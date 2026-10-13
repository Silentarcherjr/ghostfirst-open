import json
import httpx
import pytest
from ghost_checkout.agent import Agent, MockModel, OpenAICompatibleChat, BedrockConverseStub, Purchase, guarded_text
from ghost_checkout.api import RecordedGhost
from ghost_checkout.checkout import Checkout
from ghost_checkout.demo_data import records,BASE
from ghost_checkout.evidence import ClosedError
from ghost_checkout.paypal import MockPayPal

pytestmark=pytest.mark.anyio
@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.mark.parametrize('text',['This is safe.','Payment approved.','Go ahead.','Guaranteed refund.','I approve the payment.'])
async def test_output_guard(text):
    with pytest.raises(ClosedError,match='model_output_rejected'): guarded_text(text)


async def test_mock_agent_never_sees_page_prose_or_claim_and_cannot_approve():
    model=MockModel();service=Checkout(RecordedGhost(records()),MockPayPal());owner=object()
    async def human(merchants,verdict): return {'proceed':True,'merchant_id':merchants[0]}
    async def call(name,args):
        if name=='check_store': return await service.check_store(owner,args['store_url'])
        if name=='start_checkout': return await service.start_checkout(owner,**args,ask=human)
        raise AssertionError('agent tried to capture')
    agent=Agent(model,call)
    result=await agent.run(Purchase(BASE+'flash-sale.html','Kettle','12.00','USD'))
    assert result['status']=='buyer_approval_required'
    assert 'INJECTED_ACCOUNT_X' not in json.dumps(model.seen)
    assert 'DEMO_CLAIMED_MERCHANT' not in json.dumps(model.seen)
    assert service.paypal.calls==['create']


@pytest.mark.parametrize('name,args',[
    ('start_checkout',{'store_url':BASE+'corner-bakery.html','item':'Kettle','amount':'999.00','currency':'USD'}),
    ('start_checkout',{'store_url':BASE+'corner-bakery.html','item':'Kettle','amount':'12.00','currency':'USD','payee':'INJECTED'}),
    ('complete_checkout',{'order_id':'MODEL_INVENTED'}),
])
async def test_model_cannot_change_mandate_or_choose_payee_or_capture(name,args):
    class Malicious:
        async def complete(self,*_): return {'tool_calls':[{'id':'call','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
    calls=[]
    async def call(*args): calls.append(args)
    with pytest.raises(ClosedError): await Agent(Malicious(),call).run(Purchase(BASE+'corner-bakery.html','Kettle','12.00','USD'))
    assert not calls


async def test_openai_compatible_mock_transport_and_bedrock_stub():
    seen=[]
    def mock(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'Review the evidence.'}}]})
    model=OpenAICompatibleChat(httpx.MockTransport(mock))
    assert (await model.complete([{'role':'user','content':'hello'}],[]))['content']=='Review the evidence.'
    assert seen[0]['messages']==[{'role':'user','content':'hello'}]
    with pytest.raises(ClosedError): OpenAICompatibleChat(None)
    with pytest.raises(ClosedError,match='bedrock_not_configured'): await BedrockConverseStub().complete([],[])
