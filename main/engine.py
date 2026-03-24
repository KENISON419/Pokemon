from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pokechamp.ollama_player import OllamaPlayer


_DAMAGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:~|-|〜)\s*(\d+(?:\.\d+)?)")
_SINGLE_DAMAGE_RE = re.compile(r"(\d+(?:\.\d+)?)%?")
_LETHAL_RE = re.compile(r"確(\d+)|乱(\d+)")


@dataclass
class CandidateAction:
    action_id: str
    action_type: str
    score: float
    rationale: str


class IntegratedBattleEngine:
    def __init__(self, model_name: str = "llama3.1:8b", battle_format: str = "gen9ou") -> None:
        self.model_name = model_name
        self.battle_format = battle_format
        self._ollama = OllamaPlayer(model=model_name)
        self._predictor = None
        self._ja_to_en = self._load_ja_to_en_mapping()

    @staticmethod
    def _load_ja_to_en_mapping() -> dict[str, str]:
        mapping: dict[str, str] = {}
        path = Path("battle-assistant-sv-main/data/foreign_name.txt")
        if not path.exists():
            return mapping
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            mapping[parts[0]] = parts[1]
        return mapping

    @property
    def predictor(self):
        if self._predictor is None:
            from bayesian.pokemon_predictor import PokemonPredictor
            self._predictor = PokemonPredictor(battle_format=self.battle_format)
        return self._predictor

    def analyze_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        phase = snapshot.get("phase", "UNKNOWN")
        current_self = snapshot.get("currentPokemon") or {}
        current_enemy = snapshot.get("currentEnemy") or {}
        party = snapshot.get("party") or []
        enemy_team = snapshot.get("enemy") or []
        attack_rows = ((snapshot.get("ui") or {}).get("attackRows") or [])
        defence_rows = ((snapshot.get("ui") or {}).get("defenceRows") or [])

        revealed_enemy = [
            self._normalize_species(mon.get("name", ""))
            for mon in enemy_team
            if mon and mon.get("name")
        ]
        revealed_enemy = [name for name in revealed_enemy if name]
        active_enemy = self._normalize_species(current_enemy.get("name", ""))

        predictor_summary = self._build_predictor_summary(active_enemy, revealed_enemy)
        candidates = self._build_candidates(current_self, party, attack_rows, defence_rows)
        recommendation = self._rank_candidates_with_ollama(
            snapshot=snapshot,
            predictor_summary=predictor_summary,
            candidates=candidates,
        )
        if recommendation is None and candidates:
            top = max(candidates, key=lambda item: item.score)
            recommendation = {
                "action_id": top.action_id,
                "action_type": top.action_type,
                "reason": top.rationale,
                "confidence": min(0.8, max(0.45, top.score / 100.0)),
                "source": "heuristic_fallback",
            }

        return {
            "phase": phase,
            "active_self": current_self.get("name", ""),
            "active_enemy": current_enemy.get("name", ""),
            "recommendation": recommendation,
            "candidate_actions": [
                {
                    "action_id": candidate.action_id,
                    "action_type": candidate.action_type,
                    "score": round(candidate.score, 2),
                    "rationale": candidate.rationale,
                }
                for candidate in sorted(candidates, key=lambda item: item.score, reverse=True)[:6]
            ],
            "predictor_summary": predictor_summary,
            "summary": self._build_summary_text(snapshot, predictor_summary, recommendation),
        }

    def _build_predictor_summary(self, active_enemy: str, revealed_enemy: list[str]) -> dict[str, Any]:
        if not active_enemy:
            return {"available": False, "reason": "active enemy not identified"}
        try:
            config = self.predictor.predict_moveset(active_enemy, teammates=revealed_enemy)
            teammate_predictions = self.predictor.predict_teammates(revealed_enemy, max_predictions=5)
            return {
                "available": True,
                "active_enemy": active_enemy,
                "predicted_moves": config.get("moves", [])[:4],
                "predicted_item": config.get("item"),
                "predicted_ability": config.get("ability"),
                "predicted_nature": config.get("nature"),
                "predicted_tera": config.get("tera_type") or config.get("tera"),
                "predicted_probability": config.get("probability", 0),
                "teammates": teammate_predictions[:5],
            }
        except Exception as exc:
            return {
                "available": False,
                "reason": str(exc),
                "active_enemy": active_enemy,
            }

    def _build_candidates(
        self,
        current_self: dict[str, Any],
        party: list[dict[str, Any]],
        attack_rows: list[dict[str, Any]],
        defence_rows: list[dict[str, Any]],
    ) -> list[CandidateAction]:
        move_scores = self._build_move_scores(attack_rows)
        max_incoming = 0.0
        if defence_rows:
            max_incoming = max(self._parse_damage_row(row) for row in defence_rows)
        hp_ratio = self._safe_hp_ratio(current_self)

        candidates: list[CandidateAction] = []
        for move in current_self.get("move", []):
            if not move:
                continue
            damage_score = move_scores.get(move, 10.0)
            pressure_bonus = 20.0 if max_incoming >= 70 else 0.0
            score = damage_score + pressure_bonus + (10.0 if hp_ratio > 0.6 else 0.0)
            candidates.append(
                CandidateAction(
                    action_id=move,
                    action_type="move",
                    score=score,
                    rationale=f"battle-assistant damage estimate {damage_score:.1f} / incoming pressure {max_incoming:.1f}",
                )
            )

        for mon in party:
            if not mon or mon.get("name") == current_self.get("name") or not mon.get("name"):
                continue
            status = mon.get("status") or []
            hp_now = mon.get("hp") or 0
            hp_max = status[0] if status else 0
            if hp_max and hp_now == 0:
                continue
            switch_score = 30.0
            if hp_ratio < 0.3:
                switch_score += 25.0
            candidates.append(
                CandidateAction(
                    action_id=mon.get("name"),
                    action_type="switch",
                    score=switch_score,
                    rationale="preserve current active Pokémon when incoming pressure is high",
                )
            )
        return candidates

    def _build_move_scores(self, attack_rows: list[dict[str, Any]]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for row in attack_rows:
            move = row.get("move", "")
            if not move:
                continue
            damage = self._parse_damage_row(row)
            lethal_bonus = self._parse_lethal_bonus(row)
            scores[move] = damage + lethal_bonus
        return scores

    def _parse_damage_row(self, row: dict[str, Any]) -> float:
        text = " ".join(row.get("values", []))
        if not text:
            return 0.0
        match = _DAMAGE_RE.search(text)
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            return (low + high) / 2
        match = _SINGLE_DAMAGE_RE.search(text)
        if match:
            return float(match.group(1))
        return 0.0

    def _parse_lethal_bonus(self, row: dict[str, Any]) -> float:
        text = " ".join(row.get("values", []))
        match = _LETHAL_RE.search(text)
        if not match:
            return 0.0
        turns = int(match.group(1) or match.group(2) or 0)
        if turns <= 1:
            return 35.0
        if turns == 2:
            return 20.0
        if turns == 3:
            return 8.0
        return 0.0

    def _safe_hp_ratio(self, mon: dict[str, Any]) -> float:
        status = mon.get("status") or []
        max_hp = status[0] if status else 0
        hp_now = mon.get("hp") or 0
        if not max_hp:
            return 0.5
        return max(0.0, min(1.0, hp_now / max_hp))

    def _normalize_species(self, name: str) -> str:
        if not name:
            return ""
        return self._ja_to_en.get(name, name)

    def _rank_candidates_with_ollama(
        self,
        snapshot: dict[str, Any],
        predictor_summary: dict[str, Any],
        candidates: list[CandidateAction],
    ) -> dict[str, Any] | None:
        if not candidates:
            return None
        top_candidates = sorted(candidates, key=lambda item: item.score, reverse=True)[:6]
        system_prompt = (
            "You are PokéChamp integrated into a live Pokemon Scarlet/Violet battle assistant. "
            "Choose exactly one best next action from the given candidates. "
            "You must answer JSON only."
        )
        user_prompt = json.dumps(
            {
                "task": "Select the best next action for the player in a live SV singles battle.",
                "active_self": snapshot.get("currentPokemon", {}).get("name", ""),
                "active_enemy": snapshot.get("currentEnemy", {}).get("name", ""),
                "phase": snapshot.get("phase", ""),
                "weather": snapshot.get("weather", ""),
                "field": snapshot.get("field", ""),
                "current_damage_board": snapshot.get("ui", {}),
                "predictor_summary": predictor_summary,
                "candidates": [candidate.__dict__ for candidate in top_candidates],
                "output_schema": {
                    "action_id": "candidate id",
                    "action_type": "move or switch",
                    "reason": "short japanese explanation",
                    "confidence": "0.0-1.0"
                },
            },
            ensure_ascii=False,
        )
        response, is_json, _raw = self._ollama.get_LLM_action(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=self.model_name,
            temperature=0.2,
            json_format=True,
            max_tokens=300,
        )
        if not response:
            return None
        try:
            if not is_json and not response.strip().startswith("{"):
                return None
            parsed = json.loads(response)
        except json.JSONDecodeError:
            return None
        action_id = parsed.get("action_id")
        action_type = parsed.get("action_type")
        if not action_id or not action_type:
            return None
        valid_ids = {(candidate.action_id, candidate.action_type) for candidate in top_candidates}
        if (action_id, action_type) not in valid_ids:
            return None
        confidence = parsed.get("confidence", 0.6)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = 0.6
        confidence = max(0.0, min(1.0, float(confidence)))
        return {
            "action_id": action_id,
            "action_type": action_type,
            "reason": parsed.get("reason", "PokéChamp (Ollama) recommendation"),
            "confidence": confidence,
            "source": "ollama",
        }

    def _build_summary_text(
        self,
        snapshot: dict[str, Any],
        predictor_summary: dict[str, Any],
        recommendation: dict[str, Any] | None,
    ) -> str:
        active_self = snapshot.get("currentPokemon", {}).get("name", "不明")
        active_enemy = snapshot.get("currentEnemy", {}).get("name", "不明")
        recommendation_text = "提案なし"
        if recommendation:
            recommendation_text = f"{recommendation['action_type']}:{recommendation['action_id']}"
        predictor_text = "Bayesian予測なし"
        if predictor_summary.get("available"):
            predictor_text = (
                f"相手想定 item={predictor_summary.get('predicted_item')}, "
                f"ability={predictor_summary.get('predicted_ability')}, "
                f"moves={','.join(predictor_summary.get('predicted_moves', [])[:3])}"
            )
        return (
            f"自分:{active_self} / 相手:{active_enemy} / 推奨:{recommendation_text} / "
            f"{predictor_text}"
        )
