import asyncio
import httpx
import pytest
from mcp.client import Client
from ghostfirst_mcp.jobs import Jobs
from ghostfirst_mcp.server import build_server
from test_server import PHISHING_SCAN, fake_api

pytestmark = pytest.mark.anyio

@pytest.fixture
def anyio_backend():
    return 'asyncio'

async def test_job_ack_is_fast_and_other_connection_cannot_poll():
    gate = asyncio.Event()
    seen = []
    async def handler(request):
        seen.append(request)
        await gate.wait()
        return httpx.Response(200, json=PHISHING_SCAN)
    from ghostfirst_mcp.api import GhostFirstClient
    server = build_server(GhostFirstClient('https://api.test', transport=httpx.MockTransport(handler)))
    async with Client(server, mode='legacy') as first, Client(server, mode='legacy') as other:
        ack = (await asyncio.wait_for(first.call_tool('check_link', {'url': 'https://a.example/'}), .5)).structured_content
        assert ack['status'] == 'checking' and ack['verdict'] is None
        poll = {'job_id': ack['job_id']}
        denied = (await other.call_tool('get_check_result', poll)).structured_content
        unknown = (await other.call_tool('get_check_result', {'job_id': 'unknown'})).structured_content
        assert denied == unknown and denied['error_code'] == 'job_not_found'
        assert (await first.call_tool('get_check_result', poll)).structured_content['status'] == 'checking'
        gate.set()
        await asyncio.sleep(.02)
        assert (await first.call_tool('get_check_result', poll)).structured_content['verdict'] == 'do_not_continue'

async def test_bad_api_payload_fails_closed():
    server = build_server(fake_api([httpx.Response(200, text='not json')], []))
    from test_server import call
    out = await call(server, 'check_link', 'https://a.example/')
    assert out['status'] == 'error' and out['verdict'] is None

async def test_expiry_and_disconnect_cancel_work(monkeypatch):
    import ghostfirst_mcp.jobs as module
    monkeypatch.setattr(module, 'JOB_TTL', .01)
    jobs = Jobs()
    owner = object()
    async def pending():
        await asyncio.Event().wait()
    key = jobs.start(owner, pending)
    task = jobs.get(owner, key).task
    await asyncio.sleep(.03)
    assert jobs.get(owner, key) is None and task.cancelled()
    key = jobs.start(owner, pending)
    task = jobs.get(owner, key).task
    await jobs.close_owner(owner)
    assert not jobs.entries and task.cancelled()

async def test_capacity_is_bounded(monkeypatch):
    import ghostfirst_mcp.jobs as module
    monkeypatch.setattr(module, 'MAX_SESSION_JOBS', 1)
    jobs = Jobs(); owner = object()
    async def pending():
        await asyncio.Event().wait()
    assert jobs.start(owner, pending)
    assert jobs.start(owner, pending) is None
    await jobs.close_owner(owner)
