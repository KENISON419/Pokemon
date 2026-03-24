from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import threading
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import websockets

from main.engine import IntegratedBattleEngine


REPO_ROOT = Path(__file__).resolve().parent.parent


class RepoHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/main/index.html"
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def guess_type(self, path: str) -> str:
        guessed = mimetypes.guess_type(path)[0]
        return guessed or "application/octet-stream"


@dataclass
class RuntimeConfig:
    host: str
    http_port: int
    ws_port: int
    ollama_model: str


class IntegrationRuntime:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.engine = IntegratedBattleEngine(model_name=config.ollama_model)

    async def websocket_handler(self, websocket: Any) -> None:
        async for raw_message in websocket:
            response = await self._handle_message(raw_message)
            await websocket.send(json.dumps(response, ensure_ascii=False))

    async def _handle_message(self, raw_message: str) -> dict[str, Any]:
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            return {"type": "error", "payload": {"message": f"invalid json: {exc}"}}

        message_type = message.get("type")
        if message_type == "hello":
            return {
                "type": "hello",
                "payload": {
                    "ws_port": self.config.ws_port,
                    "http_port": self.config.http_port,
                    "ollama_model": self.config.ollama_model,
                    "status": "ready",
                },
            }
        if message_type == "state_update":
            snapshot = message.get("payload", {}).get("snapshot", {})
            analysis = self.engine.analyze_snapshot(snapshot)
            return {"type": "analysis", "payload": analysis}
        return {"type": "error", "payload": {"message": f"unsupported message type: {message_type}"}}


def start_http_server(config: RuntimeConfig) -> ThreadingHTTPServer:
    handler = partial(RepoHTTPRequestHandler, directory=str(REPO_ROOT))
    server = ThreadingHTTPServer((config.host, config.http_port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def serve_websocket(config: RuntimeConfig) -> None:
    runtime = IntegrationRuntime(config)
    async with websockets.serve(runtime.websocket_handler, config.host, config.ws_port):
        print(f"[main] WebSocket server started at ws://{config.host}:{config.ws_port}/")
        await asyncio.Future()


def parse_args() -> RuntimeConfig:
    parser = argparse.ArgumentParser(description="Integrated battle-assistant-sv-main + pokechamp runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--ws-port", type=int, default=8765)
    parser.add_argument("--ollama-model", default="llama3.1:8b")
    args = parser.parse_args()
    return RuntimeConfig(
        host=args.host,
        http_port=args.http_port,
        ws_port=args.ws_port,
        ollama_model=args.ollama_model,
    )


def main() -> None:
    config = parse_args()
    start_http_server(config)
    print(f"[main] HTTP server started at http://{config.host}:{config.http_port}/")
    asyncio.run(serve_websocket(config))


if __name__ == "__main__":
    main()
