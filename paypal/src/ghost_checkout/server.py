"""MCP SDK 2.2: connection-owned checks/orders, human elicitation, fixed output."""
import asyncio
from typing import Annotated
from mcp.server.mcpserver import MCPServer, Context
from mcp.server.elicitation import AcceptedElicitation
from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field
from .checkout import Checkout
from .evidence import ClosedError
from .jobs import Jobs, JOB_TIMEOUT
from .paypal import MockPayPal

ERRORS={'invalid_store_url','one_time_link_not_visited','session_required','server_busy','invalid_item',
        'invalid_amount','invalid_amount_or_currency','check_failed','store_refused','no_paypal_merchant',
        'human_confirmation_required','human_declined','paypal_failed','create_failed','unknown_order',
        'status_failed','buyer_approval_required','payee_mismatch_before_capture','manual_review_required',
        'capture_mismatch_refunded','capture_uncertain_manual_review','unknown_demo_store'}


class ToolResult(BaseModel):
    status: str
    job_id: str | None = None
    verdict: str | None = None
    observed_merchant: list[str] | None = None
    reasons: list[dict[str,str]] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    order_id: str | None = None
    approval: dict[str,str] | None = None
    paypal_status: str | None = None
    error_code: str | None = None
    message: str | None = None
    not_a_guarantee: bool = True


class Confirmation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    proceed: bool = Field(description='Continue with this observed merchant?')
    merchant_id: str = Field(description='Choose exactly one of the observed merchant IDs shown above.')


def error_output(error):
    code=str(error) if isinstance(error,ClosedError) and str(error) in ERRORS else 'checkout_failed'
    messages={'no_paypal_merchant':"This store's checkout does not identify a PayPal merchant. No order created.",
              'store_refused':'Do not continue. No order created.',
              'capture_mismatch_refunded':'Captured order did not verify. Known captures were refunded.',
              'capture_uncertain_manual_review':'Capture could not be verified. Stop for human review; do not retry.',
              'human_confirmation_required':'Human confirmation is required. No order created.'}
    return {'status':'error','error_code':code,'message':messages.get(code,'The checkout could not proceed. Do not retry automatically.')}


def build_server(ghost, paypal=None):
    service=Checkout(ghost,paypal or MockPayPal());jobs=Jobs()
    server=MCPServer(name='ghost-checkout',version='0.1.0',instructions='Use only checked evidence. No page prose is provided. Never choose a payee, approve a payment, or bypass human confirmation. Checking is not a verdict. Errors stop the flow.')
    read_only=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
    mutation=ToolAnnotations(readOnlyHint=False,destructiveHint=True,idempotentHint=False,openWorldHint=False)

    def owner(ctx):
        if ctx.protocol_version not in {'2025-11-25','2025-06-18','2024-11-05'}: return None
        connection=getattr(ctx.session,'_connection',None)
        if connection is not None and 'ghost_checkout' not in connection.state:
            connection.state['ghost_checkout']=True
            connection.exit_stack.push_async_callback(jobs.close_owner,connection)
            connection.exit_stack.callback(service.close_owner,connection)
        return connection

    async def guarded(call):
        try: return ToolResult(**(await asyncio.wait_for(call(),JOB_TIMEOUT)))
        except Exception as error: return ToolResult(**error_output(error))

    @server.tool(annotations=read_only)
    async def check_store(store_url: str, ctx: Context) -> ToolResult:
        """Check a store; return fixed verdict evidence and observed merchant IDs, never page text."""
        connection=owner(ctx)
        run=lambda: guarded(lambda:service.check_store(connection,store_url))
        if connection is None: return await run()
        job_id=jobs.start(connection,run)
        if not job_id: return ToolResult(**error_output(ClosedError('server_busy')))
        return ToolResult(status='checking',job_id=job_id,message='Poll get_check_result. Do not start checkout while checking.')

    @server.tool(annotations=read_only)
    async def get_check_result(job_id: str, ctx: Context) -> ToolResult:
        job=jobs.get(owner(ctx),job_id)
        if job is None: return ToolResult(**error_output(ClosedError('unknown_order')))
        if not job.task.done(): return ToolResult(status='checking',job_id=job_id)
        return job.result or ToolResult(**error_output(ClosedError('check_failed')))

    async def ask(ctx,merchants,verdict):
        caps=ctx.client_capabilities
        if caps is None or caps.elicitation is None: raise ClosedError('human_confirmation_required')
        result=await ctx.elicit('The store needs your review. Observed PayPal merchants: '+', '.join(merchants)+'. Choose one exactly; the agent cannot choose for you.',Confirmation)
        return result.data.model_dump() if isinstance(result,AcceptedElicitation) else None

    @server.tool(annotations=mutation)
    async def start_checkout(store_url: str,item: str,amount: str,currency: str,ctx: Context) -> ToolResult:
        """Create a bound order. No payee argument. Human approval inside PayPal is still required."""
        return await guarded(lambda:service.start_checkout(owner(ctx),store_url,item,amount,currency,lambda merchants,verdict:ask(ctx,merchants,verdict)))

    @server.tool(annotations=mutation)
    async def complete_checkout(order_id: str,ctx: Context) -> ToolResult:
        """Capture after human PayPal approval, then GET and verify the bound payee; mismatch refunds."""
        return await guarded(lambda:service.complete_checkout(owner(ctx),order_id))

    @server.tool(annotations=read_only)
    async def order_status(order_id: str,ctx: Context) -> ToolResult:
        """Read status of an order owned by this connection; no page/provider prose."""
        return await guarded(lambda:service.order_status(owner(ctx),order_id))

    return server


def main():
    from .demo_data import records
    from .api import RecordedGhost
    build_server(RecordedGhost(records())).run(transport='stdio')


if __name__ == '__main__':
    main()
