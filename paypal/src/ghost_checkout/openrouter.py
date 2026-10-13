"""Small budget, sequential client tools, fixed endpoints and redacted errors."""
from copy import deepcopy
from decimal import Decimal
import json
import logging
import httpx
from .agent import guarded_text
from .config import OPENROUTER_BASE
from .evidence import ClosedError


class OpenRouterChat:
    def __init__(self,config,transport=None,max_calls=6):
        if config.llm_base!=OPENROUTER_BASE or config.llm_model!='anthropic/claude-haiku-5.5' or not 1<=max_calls<=6: raise ClosedError('model_configuration_invalid')
        for name in ('httpx','httpcore'): logging.getLogger(name).setLevel(logging.CRITICAL)
        self.config,self.transport=config,transport
        self.max_calls=max_calls;self.calls=0;self.cost=Decimal('0');self.cassette=[]

    async def complete(self,messages,tools):
        if self.calls>=self.max_calls: raise ClosedError('model_step_limit')
        if len(json.dumps(messages))>40000: raise ClosedError('model_context_limit')
        self.calls+=1 # Reserve before network; no retries after timeout/error.
        # Restrict this client to the requested model, no server tools or fallback models.
        redacted_messages=json.loads(self.config.redact(json.dumps(messages)))
        payload={'model':self.config.llm_model,'messages':redacted_messages,'tools':tools,
                 'max_completion_tokens':384,'parallel_tool_calls':False,'temperature':0,
                 'provider':{'allow_fallbacks':False,'max_price':{'prompt':0.11,'completion':0.55,'request':0}},
                 'reasoning':{'enabled':False},'usage':{'include':True}}
        try:
            async with httpx.AsyncClient(transport=self.transport,timeout=30,trust_env=False,follow_redirects=False) as client:
                response=await client.post(OPENROUTER_BASE+'/chat/completions',json=payload,
                    headers={'Authorization':'Bearer '+self.config.llm_key.get_secret_value()})
            if response.status_code!=200: raise ValueError()
            raw=response.json();usage=raw.get('usage',{})
            cost=Decimal(str(usage['cost']))
            if not cost.is_finite() or cost<0: raise ValueError()
            self.cost+=cost
            if self.cost>=Decimal('.10'): raise ClosedError('model_budget_limit')
            message=raw['choices'][0]['message']
            calls=message.get('tool_calls') or []
            if len(calls)>1: raise ClosedError('model_tool_rejected')
            # Do not persist reasoning, provider metadata, headers or error bodies.
            shaped={'role':'assistant','content':None}
            if calls:
                call=calls[0]
                if call.get('type')!='function' or len(call.get('id',''))>128: raise ValueError()
                shaped['tool_calls']=[{'id':call['id'],'type':'function','function':{
                    'name':call['function']['name'],'arguments':call['function']['arguments']}}]
            else: shaped['content']=guarded_text(message.get('content'))
            serialized=json.dumps(shaped,ensure_ascii=False)
            if self.config.redact(serialized)!=serialized: raise ClosedError('model_output_rejected')
            self.cassette.append({'request':{'messages':deepcopy(redacted_messages),'tools':deepcopy(tools)},
                'response':deepcopy(shaped),'usage':{key:usage.get(key,0) for key in ('prompt_tokens','completion_tokens','cost')}})
            return shaped
        except ClosedError: raise
        except Exception: raise ClosedError('model_failed') from None
