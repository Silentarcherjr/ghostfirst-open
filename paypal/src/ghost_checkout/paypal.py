"""APIMatic model/controller adapter with injected mock controllers only in E3–E5."""
import asyncio
import json
from paypalserversdk.api_helper import APIHelper
from copy import deepcopy
from secrets import token_urlsafe
from paypalserversdk.models.order_request import OrderRequest
from .evidence import ClosedError


# Where PayPal sends the buyer after approval. Without it, the sandbox
# approval page reloads itself instead of finishing.
RETURN_URL='https://ghostfirst.com/?paypal=approved'
CANCEL_URL='https://ghostfirst.com/?paypal=cancelled'


def order_body(merchant, item, amount, currency):
    body={'intent':'CAPTURE','purchase_units':[{'description':item,
          'amount':{'currency_code':currency,'value':amount},'payee':{'merchant_id':merchant}}],
          'payment_source':{'paypal':{'experience_context':{'return_url':RETURN_URL,'cancel_url':CANCEL_URL,
              'user_action':'PAY_NOW','shipping_preference':'NO_SHIPPING'}}}}
    # Exercise the actual installed APIMatic model serializer even offline.
    return json.loads(APIHelper.json_serialize(OrderRequest.from_dictionary(body)))


class ServerSDKPayPal:
    """Injected controllers; SandboxPayPal wires pinned SDK OAuth for E6."""
    def __init__(self, orders, payments):
        self.orders, self.payments = orders, payments
        self.lock=asyncio.Lock();self.uncertain=False

    async def _call(self, method, options):
        async with self.lock:
            if self.uncertain: raise ClosedError('paypal_uncertain_manual_review')
            try:
                result=await asyncio.to_thread(method,options)
                if not 200 <= result.status_code < 300: raise ClosedError('paypal_failed')
                return json.loads(APIHelper.json_serialize(result.body))
            except asyncio.CancelledError:
                self.uncertain=True
                raise
            except Exception:
                raise ClosedError('paypal_failed') from None

    async def create(self, body, request_id):
        return await self._call(self.orders.create_order,{'body':OrderRequest.from_dictionary(body),'paypal_request_id':request_id})

    async def get(self, order_id):
        return await self._call(self.orders.get_order,{'id':order_id})

    async def capture(self, order_id, request_id):
        return await self._call(self.orders.capture_order,{'id':order_id,'paypal_request_id':request_id})

    async def refund(self, capture_id, request_id):
        return await self._call(self.payments.refund_captured_payment,{'capture_id':capture_id,'paypal_request_id':request_id})


class MockPayPal:
    """Volatile orders. approve() exists for the human UI/test driver, never MCP/LLM."""
    def __init__(self):
        self.orders={}; self.calls=[]; self.refunds=[]; self.fail=None; self.mismatch=False

    def _guard(self, action):
        self.calls.append(action)
        if self.fail == action: raise ClosedError('paypal_failed')

    async def create(self, body, request_id):
        self._guard('create')
        if len(self.orders)>=128: raise ClosedError('server_busy')
        order_id='MOCK-'+token_urlsafe(18)
        order=deepcopy(body);order.update(id=order_id,status='CREATED')
        self.orders[order_id]=order
        return deepcopy(order)

    async def get(self, order_id):
        self._guard('get'); return deepcopy(self.orders[order_id])

    async def approve(self, order_id):
        if self.orders[order_id]['status'] != 'CREATED': raise ClosedError('approval_failed')
        self.orders[order_id]['status']='APPROVED'

    async def capture(self, order_id, request_id):
        self._guard('capture')
        order=self.orders[order_id]
        if order['status'] != 'APPROVED': raise ClosedError('buyer_approval_required')
        order['status']='COMPLETED'
        for i,unit in enumerate(order['purchase_units']):
            unit['payments']={'captures':[{'id':'MOCK-CAPTURE-'+order_id+'-'+str(i),'status':'COMPLETED',
                                           'amount':deepcopy(unit['amount'])}]}
            if self.mismatch: unit['payee']['merchant_id']='MOCK_WRONG_MERCHANT'
        # Same shape as PayPal's capture response: purchase units carry the
        # captures (with their amounts) but no payee and no order-level amount.
        return {'id':order['id'],'status':order['status'],'purchase_units':[
            {'reference_id':u.get('reference_id','default'),'payments':deepcopy(u['payments'])}
            for u in order['purchase_units']]}

    async def refund(self, capture_id, request_id):
        self._guard('refund');self.refunds.append(capture_id)
        return {'status':'COMPLETED'}
