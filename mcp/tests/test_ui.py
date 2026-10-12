import pytest
from mcp.client import Client
from ghostfirst_mcp.server import build_server
from ghostfirst_mcp import ui

pytestmark = pytest.mark.anyio
@pytest.fixture
def anyio_backend(): return 'asyncio'

async def test_apps_resource_and_tool_linkage():
    async with Client(build_server(), mode='legacy') as client:
        tools = (await client.list_tools()).tools
        assert all(t.meta['ui']['resourceUri'] == ui.URI for t in tools if t.name != 'share_link')
        resource = await client.read_resource(ui.URI)
        assert resource.contents[0].mime_type == ui.MIME
        assert resource.contents[0].text == ui.HTML
        assert resource.contents[0].meta['ui']['csp']['connectDomains'] == []
        assert '__SCRIPT__' not in ui.HTML and ui.SCRIPT_HASH in ui.HTML
        assert 'innerHTML' not in ui.SCRIPT
        assert '<img' not in ui.HTML and 'fetch(' not in ui.SCRIPT
