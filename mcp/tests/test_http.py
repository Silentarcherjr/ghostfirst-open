"""Streamable HTTP mode: the wire path a browser client (the simulator) uses."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from ghostfirst_mcp.server import SIMULATOR_DIR, build_http_app, main

from test_server import PHISHING_SCAN, fake_api

PROTOCOL = "2025-11-25"
ACCEPT = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def served():
    """Run the HTTP app on a real local port; yield (base_url, requests the fake API saw)."""
    seen: list[dict] = []
    app = build_http_app(fake_api([httpx.Response(200, json=PHISHING_SCAN)], seen))
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", seen
    server.should_exit = True
    thread.join(timeout=5)


def events(response: httpx.Response):
    for line in response.iter_lines():
        if line.startswith("data:"):
            yield json.loads(line[5:].strip())


def handshake(http: httpx.Client, base: str) -> dict:
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": PROTOCOL, "capabilities": {"elicitation": {"form": {}}},
        "clientInfo": {"name": "test", "version": "0"}}}
    with http.stream("POST", f"{base}/mcp", headers=ACCEPT, json=init) as response:
        assert response.status_code == 200
        session = response.headers["mcp-session-id"]
        result = next(events(response))["result"]
    assert result["protocolVersion"] == PROTOCOL
    headers = {**ACCEPT, "Mcp-Session-Id": session, "MCP-Protocol-Version": PROTOCOL}
    assert http.post(f"{base}/mcp", headers=headers,
                     json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    return headers


def call_tool(http: httpx.Client, base: str, headers: dict, url: str, answer: dict | None) -> tuple[dict, list]:
    asked = []
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "check_link", "arguments": {"url": url}}}
    with http.stream("POST", f"{base}/mcp", headers=headers, json=body) as response:
        for message in events(response):
            if message.get("method") == "elicitation/create":
                asked.append(message["params"]["message"])
                reply = {"jsonrpc": "2.0", "id": message["id"], "result": answer}
                assert http.post(f"{base}/mcp", headers=headers, json=reply).status_code == 202
            elif message.get("id") == 2:
                out = message["result"]["structuredContent"]
                if out["status"] == "checking":
                    return poll(http, base, headers, out["job_id"]), asked
                return out, asked
    raise AssertionError("no tool result")


def poll(http, base, headers, job_id):
    for i in range(100):
        response = http.post(f"{base}/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 10 + i,
            "method": "tools/call", "params": {"name": "get_check_result", "arguments": {"job_id": job_id}}})
        out = list(events(response))[-1]["result"]["structuredContent"]
        if out["status"] != "checking":
            return out
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_browser_style_client_checks_a_link(served) -> None:
    base, seen = served
    with httpx.Client(timeout=10) as http:
        headers = handshake(http, base)
        out, asked = call_tool(http, base, headers, "https://bit.ly/x", None)
    assert out["verdict"] == "do_not_continue"
    assert asked == []
    assert seen[0]["confirm_sensitive_link"] is False


def test_one_time_link_waits_for_the_human_on_the_same_stream(served) -> None:
    base, seen = served
    with httpx.Client(timeout=10) as http:
        headers = handshake(http, base)
        answer = {"action": "accept", "content": {"visit_anyway": True}}
        out, asked = call_tool(http, base, headers, "https://x.example/reset?token=abc123", answer)
    assert "one-time link" in asked[0]
    assert out["status"] == "checked"
    assert [request["confirm_sensitive_link"] for request in seen] == [True]


def test_requests_for_another_host_are_refused(served) -> None:
    base, _ = served
    response = httpx.post(f"{base}/mcp", headers={**ACCEPT, "Host": "evil.example"}, json={})
    assert response.status_code in (403, 421)


def test_simulator_is_served_with_a_strict_policy(served) -> None:
    base, _ = served
    page = httpx.get(f"{base}/")
    assert page.status_code == 200
    policy = page.headers["content-security-policy"]
    assert "default-src 'none'" in policy and "connect-src 'self'" in policy
    assert httpx.get(f"{base}/app.js").headers["content-type"].startswith("text/javascript")


def test_simulator_loads_nothing_from_elsewhere() -> None:
    html = (SIMULATOR_DIR / "index.html").read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline scripts would break the CSP"
    for name in ("index.html", "app.js", "styles.css"):
        text = (SIMULATOR_DIR / name).read_text()
        assert not re.search(r"(src|href)=\"https?://", text), name
    script = (SIMULATOR_DIR / "app.js").read_text()
    assert "innerHTML" not in script, "server text must be inserted as text"


def test_public_bind_requires_named_hosts() -> None:
    with pytest.raises(SystemExit):
        main(["--http", "--host", "0.0.0.0"])


def test_simulator_files_exist() -> None:
    assert {p.name for p in Path(SIMULATOR_DIR).iterdir()} >= {"index.html", "app.js", "styles.css"}
