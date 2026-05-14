from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _fetch_json(url: str) -> tuple[int, dict[str, object], dict[str, str]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload, {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload, {key.lower(): value for key, value in exc.headers.items()}


def _wait_for_endpoint(url: str, expected_status: int, timeout_seconds: float = 20.0) -> tuple[dict[str, object], dict[str, str]]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status_code, payload, headers = _fetch_json(url)
            if status_code == expected_status:
                return payload, headers
            last_error = RuntimeError(f"Expected status {expected_status}, got {status_code}")
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.2)

    raise AssertionError(f"Endpoint {url} did not return {expected_status} before timeout: {last_error}")


def test_live_uvicorn_process_serves_health_readiness_and_bootstrap() -> None:
    port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "APP_BASE_URL": "http://127.0.0.1:3000",
            "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/trade",
            "CLERK_PUBLISHABLE_KEY": "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk",
            "TRADE_API_BASE_URL": f"http://127.0.0.1:{port}",
            "TELEGRAM_BOT_TOKEN": "bot",
            "TELEGRAM_CHAT_ID": "chat",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.adapters.api.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        health_payload, health_headers = _wait_for_endpoint(f"http://127.0.0.1:{port}/healthz", 200)
        readiness_payload, readiness_headers = _wait_for_endpoint(f"http://127.0.0.1:{port}/readyz", 200)
        bootstrap_payload, bootstrap_headers = _wait_for_endpoint(
            f"http://127.0.0.1:{port}/api/settings/bootstrap",
            200,
        )
        session_payload, session_headers = _wait_for_endpoint(f"http://127.0.0.1:{port}/api/session", 200)

        assert health_payload == {"status": "ok"}
        assert health_headers["x-request-id"]

        assert readiness_payload["status"] == "ok"
        assert readiness_payload["checks"]["auth"]["configured"] is True
        assert readiness_headers["x-request-id"]

        assert bootstrap_payload["app_base_url"] == "http://127.0.0.1:3000"
        assert bootstrap_payload["clerk_frontend_api_host"] == "example.clerk.accounts.dev"
        assert bootstrap_headers["x-request-id"]

        assert session_payload == {"authenticated": False, "user": None}
        assert session_headers["x-request-id"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
