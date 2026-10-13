"""Each browser session owns an actual MCP client in one lifetime worker task."""
import asyncio
from mcp.client import Client
from mcp_types import ElicitResult
from .agent import Agent, MockModel
from .evidence import ClosedError


class DemoSession:
    def __init__(self,server,paypal,model=None):
        self.server,self.paypal=server,paypal
        self.model=model or MockModel()
        self.queue=asyncio.Queue(maxsize=8);self.pending=None;self.task=None;self.agent=None

    async def ask(self,ctx,params):
        if self.pending is not None: return ElicitResult(action='decline')
        future=asyncio.get_running_loop().create_future()
        # Only bounded observed IDs from our fixed MCP prompt are exposed as data.
        self.pending={'message':params.message,'future':future}
        try:
            choice=await asyncio.wait_for(future,60)
            return ElicitResult(action='accept',content=choice)
        except Exception: return ElicitResult(action='decline')
        finally: self.pending=None

    async def _worker(self):
        async with Client(self.server,mode='legacy',elicitation_callback=self.ask) as client:
            async def call(name,args):
                result=(await client.call_tool(name,args)).structured_content
                if not isinstance(result,dict): raise ClosedError('mcp_failed')
                for _ in range(400):
                    if result.get('status')!='checking': return result
                    await asyncio.sleep(.02)
                    result=(await client.call_tool('get_check_result',{'job_id':result['job_id']})).structured_content
                raise ClosedError('check_timeout')
            self.agent=Agent(self.model,call)
            while True:
                action,payload,future=await self.queue.get()
                if action=='close': future.set_result(None);break
                try:
                    if action=='purchase': result=await self.agent.run(payload)
                    elif action=='approve':
                        if payload!=self.agent.order_id: raise ClosedError('unknown_order')
                        # This path is reachable only through a human UI POST, never tools/model.
                        from .paypal import MockPayPal
                        if not isinstance(self.paypal,MockPayPal): raise ClosedError('mock_approval_unavailable')
                        await self.paypal.approve(payload)
                        result=await self.agent.complete_after_human()
                    elif action=='capture':
                        if payload!=self.agent.order_id: raise ClosedError('unknown_order')
                        result=await self.agent.complete_after_human()
                    else: raise ClosedError('invalid_action')
                    if not future.done(): future.set_result(result)
                except Exception as error:
                    if not future.done(): future.set_exception(error)

    def start(self): self.task=asyncio.create_task(self._worker())

    async def submit(self,action,payload=None):
        if self.task.done(): raise ClosedError('session_closed')
        future=asyncio.get_running_loop().create_future()
        self.queue.put_nowait((action,payload,future))
        return await asyncio.wait_for(asyncio.shield(future),70)

    def confirm(self,proceed,merchant):
        if self.pending is None or self.pending['future'].done(): raise ClosedError('no_pending_confirmation')
        if type(proceed) is not bool: raise ClosedError('invalid_confirmation')
        self.pending['future'].set_result({'proceed':proceed,'merchant_id':merchant})

    async def close(self):
        if self.pending and not self.pending['future'].done(): self.pending['future'].set_result({'proceed':False,'merchant_id':''})
        try: await self.submit('close')
        except Exception: self.task.cancel()
        await asyncio.gather(self.task,return_exceptions=True)
