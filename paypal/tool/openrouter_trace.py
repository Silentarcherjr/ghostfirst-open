"""One authorized six-call conversation: real LLM, recorded stores, mock payments."""
import argparse
import asyncio
from datetime import datetime,timezone
import json
import logging
from pathlib import Path
from ghost_checkout.agent import Agent,Purchase
from ghost_checkout.api import RecordedGhost
from ghost_checkout.checkout import Checkout
from ghost_checkout.config import runtime_config
from ghost_checkout.demo_data import BASE,records
from ghost_checkout.evidence import ClosedError
from ghost_checkout.openrouter import OpenRouterChat
from ghost_checkout.paypal import MockPayPal
from ghost_checkout.server import error_output


async def run(output):
    if output.exists(): raise ClosedError('trace_already_exists') # No accidental paid rerun.
    config=runtime_config('sandbox');model=OpenRouterChat(config)
    paypal=MockPayPal();service=Checkout(RecordedGhost(records()),paypal);owner=object()
    history=[];episodes=[]
    async def call(name,args):
        try:
            if name=='check_store': return await service.check_store(owner,args['store_url'])
            if name=='start_checkout': return await service.start_checkout(owner,**args)
            raise ClosedError('human_payment_step_required')
        except Exception as error: return error_output(error)
    try:
        for store in ('flash-sale','riverside-deals','corner-bakery'):
            agent=Agent(model,call,history=history)
            # Prompt stays stable across episodes; only the explicit user mandate changes.
            result=await agent.run(Purchase(BASE+store+'.html','Blue kettle','1.00','USD'))
            episodes.append({'store':store,'status':result['status'],'traffic':result['traffic'],'answer':result['answer']})
            history=agent.messages
    except Exception:
        episodes.append({'status':'stopped','error_code':'conversation_stopped'})
    record={'recorded_at':datetime.now(timezone.utc).isoformat(),'model':config.llm_model,
        'mode':'real_openrouter_recorded_stores_mock_paypal','calls':model.calls,'reported_cost_usd':str(model.cost),
        'no_buyer_approval':True,'page_prose_not_sent':True,'episodes':episodes,'cassette':model.cassette}
    # Redact volatile mock order IDs from all tool histories and deterministic cassettes.
    text=json.dumps(record,indent=2,ensure_ascii=False)
    for number,order_id in enumerate(paypal.orders): text=text.replace(order_id,'MOCK-RECORDED-ORDER-'+str(number+1))
    redacted=config.redact(text)
    if redacted!=text: raise ClosedError('trace_secret_detected')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(redacted+'\n')
    print('Trace recorded; calls='+str(model.calls)+'; reported cost USD '+str(model.cost),flush=True)


def main():
    logging.disable(logging.CRITICAL)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try: asyncio.run(run(args.output))
    except BaseException:
        print('Trace stopped; no secrets or provider errors printed.',flush=True)
        raise SystemExit(1) from None


if __name__=='__main__':main()
