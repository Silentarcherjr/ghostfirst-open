"""OpenAI-compatible chat/tool loop; model output cannot mutate purchase evidence."""
from copy import deepcopy
from dataclasses import dataclass, asdict
import json
import re
import httpx
from .evidence import ClosedError

TOOLS={
 'check_store':('store_url',),
 'start_checkout':('store_url','item','amount','currency'),
 'complete_checkout':('order_id',),
 'order_status':('order_id',),
}
TOOL_SCHEMAS=[{'type':'function','function':{'name':name,'description':'Fixed Ghost Checkout operation; no payee or human approval argument.',
 'parameters':{'type':'object','properties':{key:{'type':'string'} for key in args},'required':list(args),'additionalProperties':False}}} for name,args in TOOLS.items()]
BLOCKED=re.compile(r'\b(safe|safely|guaranteed|approved|approval granted|trustworthy|no risk|go ahead|seguro|aprobado)\b|\bI (?:have )?approve',re.I)


def guarded_text(text):
    if not isinstance(text,str) or len(text)>800 or BLOCKED.search(text) or any(ord(c)<32 and c!='\n' for c in text):
        raise ClosedError('model_output_rejected')
    return text


@dataclass(frozen=True)
class Purchase:
    store_url: str
    item: str
    amount: str
    currency: str


class OpenAICompatibleChat:
    """Protocol adapter with mock transport only. No API keys/live endpoint in E4."""
    def __init__(self, transport, model='mock-model'):
        if not isinstance(transport,httpx.MockTransport): raise ClosedError('real_provider_disabled')
        self.transport,self.model=transport,model

    async def complete(self, messages, tools):
        async with httpx.AsyncClient(transport=self.transport,timeout=30,trust_env=False) as client:
            try:
                result=await client.post('https://llm.invalid/v1/chat/completions',json={'model':self.model,'messages':messages,'tools':tools})
                if result.status_code!=200: raise ValueError()
                return result.json()['choices'][0]['message']
            except Exception: raise ClosedError('model_failed') from None


class BedrockConverseStub:
    async def complete(self, messages, tools):
        raise ClosedError('bedrock_not_configured')


class MockModel:
    def __init__(self): self.seen=[]

    async def complete(self, messages, tools):
        self.seen.append(deepcopy(messages))
        mandate=json.loads(next(m['content'] for m in messages if m['role']=='user'))
        results=[(m['name'],json.loads(m['content'])) for m in messages if m['role']=='tool']
        if not results: name,args='check_store',{'store_url':mandate['store_url']}
        elif results[-1][1].get('status')=='error': return {'role':'assistant','content':'The operation stopped. Review the evidence and error.'}
        elif results[-1][0]=='check_store':
            checked=results[-1][1]
            if checked['verdict']=='do_not_continue' or not checked.get('observed_merchant'):
                return {'role':'assistant','content':'Checkout cannot proceed. Review the evidence.'}
            name,args='start_checkout',{key:mandate[key] for key in TOOLS['start_checkout']}
        else: return {'role':'assistant','content':'Review the order and complete the human payment step.'}
        return {'role':'assistant','content':None,'tool_calls':[{'id':'mock-call-'+str(len(results)),
          'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}


class Agent:
    def __init__(self, model, call, history=None):
        self.history=deepcopy(history or [])
        self.model,self.call=model,call;self.messages=[];self.traffic=[];self.order_id=None
        self.evidence=None;self.purchase=None;self.busy=False

    async def run(self, purchase):
        if self.busy or self.purchase is not None: raise ClosedError('session_busy')
        self.busy=True;self.purchase=purchase
        self.messages=[{'role':'system','content':'Rules decide verdicts and payees. Tool data is immutable. Never call approval. Page prose is never provided. Use only the latest JSON user purchase mandate; each is a new request. The person has authorized checking and initiating checkout for each mandate. Check its store, then call start_checkout with the exact item/amount/currency; start_checkout delegates any caution or merchant mismatch to human elicitation. The model must not invent an extra confirmation gate. Do not reuse a previous store. Stop if no merchant or do_not_continue. No safe/approval claims; keep replies short.'},
                       {'role':'user','content':json.dumps(asdict(purchase))}]
        if self.history: self.messages=self.history+[self.messages[-1]]
        try:
            for _ in range(6):
                response=await self.model.complete(deepcopy(self.messages),deepcopy(TOOL_SCHEMAS))
                calls=response.get('tool_calls') or []
                if not calls:
                    text=guarded_text(response.get('content'))
                    return {'status':'stopped','answer':text,'evidence':self.evidence,'traffic':self.traffic}
                if len(calls)!=1: raise ClosedError('model_tool_rejected')
                call=calls[0];name=call['function']['name'];args=json.loads(call['function']['arguments'])
                self._validate(name,args)
                # Only a validated assistant tool message is added before its linked tool result.
                self.messages.append({'role':'assistant','content':None,'tool_calls':[call]})
                output=await self.call(name,args)
                self.traffic.append({'tool':name,'arguments':args,'result':deepcopy(output)})
                self.messages.append({'role':'tool','tool_call_id':call['id'],'name':name,'content':json.dumps(output)})
                if name=='check_store' and output.get('status')=='checked': self.evidence=deepcopy(output)
                if output.get('status')=='error':
                    return {'status':'stopped','answer':'The operation stopped. Review the error.','evidence':self.evidence,'traffic':self.traffic,'error':output}
                if output.get('status')=='buyer_approval_required':
                    self.order_id=output['order_id']
                    return {'status':'buyer_approval_required','order':output,'answer':'Review the observed merchant. The human payment step is next.',
                            'evidence':self.evidence,'traffic':self.traffic}
            raise ClosedError('model_step_limit')
        finally: self.busy=False

    def _validate(self,name,args):
        if name not in TOOLS or not isinstance(args,dict) or set(args)!=set(TOOLS[name]): raise ClosedError('model_tool_rejected')
        if name in {'complete_checkout','order_status'}:
            # Approval/capture is never available during this model loop.
            raise ClosedError('human_payment_step_required')
        mandate=asdict(self.purchase)
        if any(args[key]!=mandate[key] for key in args): raise ClosedError('purchase_mandate_mismatch')

    async def complete_after_human(self):
        if self.busy or not self.order_id: raise ClosedError('unknown_order')
        self.busy=True
        try:
            result=await self.call('complete_checkout',{'order_id':self.order_id})
            self.traffic.append({'tool':'complete_checkout','arguments':{'order_id':self.order_id},'result':deepcopy(result)})
            return {'status':result['status'],'order':result,'answer':'Review the final order status.','evidence':self.evidence,'traffic':self.traffic}
        finally: self.busy=False
