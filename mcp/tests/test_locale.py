import asyncio
import httpx
import pytest
from mcp.client import Client
from mcp_types import RequestParamsMeta, ElicitResult
from ghostfirst_mcp.server import build_server
from ghostfirst_mcp import texts
from test_server import PHISHING_SCAN, DEEP, fake_api
pytestmark=pytest.mark.anyio
@pytest.fixture
def anyio_backend(): return 'asyncio'

@pytest.mark.parametrize('tool,payload,field,expected',[
 ('check_link',PHISHING_SCAN,'summary',texts.ES_SUMMARIES['impersonation_with_credentials'].format(credential=texts.ES_CREDENTIALS['password'],brand='PayPal')),
 ('deep_check',DEEP,'comparison',texts.ES_COMPARISONS['meaningful_variation'][0]),
])
async def test_spanish_result_retains_original_locale_when_polled(tool,payload,field,expected):
    async with Client(build_server(fake_api([httpx.Response(200,json=payload)],[])),mode='legacy') as c:
        out=(await c.call_tool(tool,{'url':'https://a.example/'},meta=RequestParamsMeta(locale='es-US'))).structured_content
        assert out['locale']=='es-US' and out['agent_guidance'].startswith('La revisión')
        while out['status']=='checking':
            await asyncio.sleep(.01)
            out=(await c.call_tool('get_check_result',{'job_id':out['job_id']})).structured_content
        assert out[field]==expected and out['locale']=='es-US'
        assert out['not_a_guarantee']==texts.ES_NOT_A_GUARANTEE

async def test_spanish_human_question_and_error_are_fixed():
    seen=[]
    async def human(context,params):
        assert params.message==texts.ES_CONSENT and not seen
        return ElicitResult(action='decline')
    async with Client(build_server(fake_api([],seen)),mode='legacy',elicitation_callback=human) as c:
        out=(await c.call_tool('check_link',{'url':'https://a.example/reset?token=abcdef'},meta=RequestParamsMeta(locale='es-MX'))).structured_content
        assert out['status']=='declined_by_human' and out['agent_guidance'].startswith('Este enlace')
        assert not seen
