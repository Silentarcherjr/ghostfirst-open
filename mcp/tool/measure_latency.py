"""Loopback MCP tool round trips with a deliberately slow, fake API. No external calls."""
import asyncio
import json
import logging
import math
import socket
import statistics
import threading
import time

import httpx
import uvicorn
from ghostfirst_mcp.api import GhostFirstClient
from ghostfirst_mcp.server import build_http_app


def rpc(http, base, headers, method, params, ident=1):
    response = http.post(base + '/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': ident,
                                                           'method': method, 'params': params})
    response.raise_for_status()
    messages = [json.loads(line[5:]) for line in response.iter_lines() if line.startswith('data:')]
    return messages[-1]['result'], response.headers


def main():
    async def slow(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json={'verdict': {'state': 'caution'}})
    logging.disable(logging.CRITICAL)
    app = build_http_app(GhostFirstClient('https://fake.example', transport=httpx.MockTransport(slow)))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    while not server.started:
        time.sleep(.01)
    timings = {name: [] for name in ['check_link', 'deep_check', 'get_check_result']}
    base = f'http://127.0.0.1:{port}'
    try:
        with httpx.Client(timeout=10) as http:
            for sample in range(100):
                headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
                _, response_headers = rpc(http, base, headers, 'initialize', {'protocolVersion': '2025-11-25',
                    'capabilities': {}, 'clientInfo': {'name': 'latency-fixture', 'version': '1'}})
                headers.update({'Mcp-Session-Id': response_headers['mcp-session-id'], 'MCP-Protocol-Version': '2025-11-25'})
                http.post(base + '/mcp', headers=headers, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                job_id = None
                for tool in timings:
                    args = {'job_id': job_id} if tool == 'get_check_result' else {'url': 'https://fixture.example/'}
                    started = time.perf_counter()
                    result, _ = rpc(http, base, headers, 'tools/call', {'name': tool, 'arguments': args}, sample + 2)
                    timings[tool].append((time.perf_counter() - started) * 1000)
                    out = result['structuredContent']
                    assert out['status'] == 'checking', out
                    job_id = out['job_id']
                http.delete(base + '/mcp', headers=headers)
    finally:
        server.should_exit = True; thread.join(5)
    for name, values in timings.items():
        print(f'{name}: n={len(values)}, median={statistics.median(values):.2f} ms, '
              f'p95={sorted(values)[math.ceil(.95 * len(values)) - 1]:.2f} ms, max={max(values):.2f} ms')

if __name__ == '__main__':
    main()
