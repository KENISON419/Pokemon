from main.engine import IntegratedBattleEngine


def make_engine():
    engine = IntegratedBattleEngine(model_name="llama3.1:8b")
    engine._build_predictor_summary = lambda active_enemy, revealed_enemy: {
        "available": True,
        "active_enemy": active_enemy,
        "predicted_moves": ["Extreme Speed", "Earthquake"],
        "predicted_item": "Choice Band",
        "predicted_ability": "Multiscale",
        "predicted_tera": "Normal",
    }
    engine._rank_candidates_with_ollama = lambda snapshot, predictor_summary, candidates: None
    return engine


def test_damage_row_parsing_supports_ranges_and_lethal_flags():
    engine = make_engine()
    row = {"values": ["57~68%", "確2"]}
    assert engine._parse_damage_row(row) == 62.5
    assert engine._parse_lethal_bonus(row) == 20.0


def test_analyze_snapshot_returns_heuristic_recommendation_when_ollama_unavailable():
    engine = make_engine()
    snapshot = {
        "phase": "BATTLE",
        "currentPokemon": {
            "name": "カイリュー",
            "move": ["しんそく", "じしん", "りゅうのまい", "ほのおのパンチ"],
            "status": [167, 204, 115, 120, 120, 132],
            "hp": 120,
        },
        "currentEnemy": {"name": "サーフゴー"},
        "party": [
            {"name": "カイリュー", "status": [167, 204, 115, 120, 120, 132], "hp": 120},
            {"name": "ハバタクカミ", "status": [130, 100, 75, 187, 156, 205], "hp": 130},
        ],
        "enemy": [{"name": "サーフゴー"}],
        "ui": {
            "attackRows": [
                {"move": "しんそく", "values": ["62~74%", "乱2(90%)"]},
                {"move": "じしん", "values": ["48~57%", "乱2(20%)"]},
            ],
            "defenceRows": [
                {"move": "ゴールドラッシュ", "values": ["72~86%", "乱1(25%)"]},
            ],
        },
        "enemyHPratio": [1, 1, 1, 1, 1, 1],
    }
    result = engine.analyze_snapshot(snapshot)
    assert result["recommendation"]["action_id"] == "しんそく"
    assert result["recommendation"]["source"] == "heuristic_fallback"
    assert result["candidate_actions"]
