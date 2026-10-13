"""Rules bind the payee; every mutation is owned, serialized and fail closed."""
import asyncio
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
from secrets import token_urlsafe
import time
from .evidence import ClosedError, sanitize, store_url, ID
from .paypal import order_body

CURRENCIES={'USD','EUR','GBP','MXN','BRL','CAD'}


@dataclass
class BoundOrder:
    owner: object
    merchant: str
    amount: str
    currency: str
    state: str = 'created'
    expires: float = field(default_factory=lambda:time.monotonic()+900)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Checkout:
    def __init__(self, ghost, paypal):
        self.ghost,self.paypal=ghost,paypal
        self.checks={};self.orders={};self.locks={};self.attempts={}

    def purge(self):
        now=time.monotonic()
        self.checks={k:v for k,v in self.checks.items() if now-v[0]<600}
        self.orders={k:v for k,v in self.orders.items() if v.expires>now}

    def close_owner(self, owner):
        self.checks={k:v for k,v in self.checks.items() if k[0] is not owner}
        self.orders={k:v for k,v in self.orders.items() if v.owner is not owner}
        self.locks.pop(owner,None)
        self.attempts={k:v for k,v in self.attempts.items() if k[0] is not owner}

    async def check_store(self, owner, url):
        url=store_url(url);self.purge()
        checked=sanitize(await asyncio.wait_for(self.ghost.scan(url),60))
        if owner is not None:
            if len(self.checks)>=1024: raise ClosedError('server_busy')
            self.checks[(owner,url)]=(time.monotonic(),checked)
        return checked.output()

    async def start_checkout(self, owner, store_url, item, amount, currency, ask=None):
        if owner is None: raise ClosedError('session_required')
        if len(self.locks)>=128 and owner not in self.locks: raise ClosedError('server_busy')
        lock=self.locks.setdefault(owner,asyncio.Lock())
        async with lock:
            return await self._start(owner,store_url,item,amount,currency,ask)

    async def _start(self, owner, url, item, amount, currency, ask):
        store_url(url);self.purge()
        if not isinstance(item,str) or not 1<=len(item)<=120 or any(ord(c)<32 for c in item): raise ClosedError('invalid_item')
        if not isinstance(amount,str) or not re.fullmatch(r'[0-9]{1,6}\.[0-9]{2}',amount): raise ClosedError('invalid_amount')
        try: value=Decimal(amount)
        except InvalidOperation: raise ClosedError('invalid_amount') from None
        if not 0<value<=Decimal('10000.00') or currency not in CURRENCIES: raise ClosedError('invalid_amount_or_currency')
        if len(self.orders)>=128: raise ClosedError('server_busy')
        if (owner,url) not in self.checks: await self.check_store(owner,url)
        checked=self.checks[(owner,url)][1]
        if checked.verdict=='do_not_continue': raise ClosedError('store_refused')
        if not checked.merchants: raise ClosedError('no_paypal_merchant')
        merchant=checked.merchants[0]
        needs_human=(checked.verdict=='caution' or len(checked.merchants)>1 or
                     checked.claimed is not None and checked.claimed!=merchant)
        if needs_human:
            if ask is None: raise ClosedError('human_confirmation_required')
            choice=await ask(checked.merchants,checked.verdict)
            if not isinstance(choice,dict) or choice.get('proceed') is not True or choice.get('merchant_id') not in checked.merchants:
                raise ClosedError('human_declined')
            merchant=choice['merchant_id']
        attempt=(owner,url,item,amount,currency)
        if attempt in self.attempts:
            raise ClosedError('manual_review_required')
        if len(self.attempts)>=128: raise ClosedError('server_busy')
        # Reserve before the external mutation. An uncertain create must not repeat.
        self.attempts[attempt]=None
        response=await asyncio.wait_for(self.paypal.create(order_body(merchant,item,amount,currency),token_urlsafe(24)),30)
        order_id=response.get('id')
        if not isinstance(order_id,str) or not ID.fullmatch(order_id) or order_id in self.orders: raise ClosedError('create_failed')
        self.orders[order_id]=BoundOrder(owner,merchant,amount,currency)
        self.attempts[attempt]=order_id
        return {'status':'buyer_approval_required','order_id':order_id,'observed_merchant':[merchant],
                'approval':{'mode':'mock','action':'human_paypal_ui'},'verdict':checked.verdict,'not_a_guarantee':True}

    def bound(self, owner, order_id):
        self.purge();order=self.orders.get(order_id)
        if owner is None or order is None or order.owner is not owner: raise ClosedError('unknown_order')
        return order

    def matches(self, raw, bound):
        try:
            units=raw['purchase_units']
            return len(units)==1 and units[0]['payee']['merchant_id']==bound.merchant and units[0]['amount']=={'currency_code':bound.currency,'value':bound.amount}
        except (KeyError, TypeError): return False

    def capture_ids(self, raw):
        try:
            captures=[c for unit in raw['purchase_units'] for c in unit['payments']['captures']]
            if not captures or len(captures)>10:
                raise ValueError()
            if any(c.get('status')!='COMPLETED' or not isinstance(c.get('id'),str) or not ID.fullmatch(c['id']) for c in captures):
                raise ValueError()
            ids={c['id'] for c in captures}
            if len(ids)!=len(captures): raise ValueError()
            return ids
        except (KeyError,TypeError,ValueError,AttributeError):
            raise ClosedError('capture_not_verified') from None

    async def order_status(self, owner, order_id):
        bound=self.bound(owner,order_id)
        raw=await asyncio.wait_for(self.paypal.get(order_id),30)
        state=raw.get('status')
        if state not in {'CREATED','APPROVED','COMPLETED','VOIDED','PAYER_ACTION_REQUIRED'}: raise ClosedError('status_failed')
        return {'status':bound.state,'paypal_status':state,'order_id':order_id,'observed_merchant':[bound.merchant]}

    async def complete_checkout(self, owner, order_id):
        bound=self.bound(owner,order_id)
        async with bound.lock:
            if bound.state=='captured': return {'status':'captured','order_id':order_id,'observed_merchant':[bound.merchant]}
            if bound.state!='created': raise ClosedError('manual_review_required')
            try:
                before=await asyncio.wait_for(self.paypal.get(order_id),30)
                if before.get('status')!='APPROVED': raise ClosedError('buyer_approval_required')
                if before.get('id')!=order_id or not self.matches(before,bound): raise ClosedError('payee_mismatch_before_capture')
            except ClosedError: raise
            except Exception: raise ClosedError('paypal_failed') from None
            # No repeated capture after timeout/error/uncertain success.
            bound.state='capture_pending'
            captured=None
            try:
                captured=await asyncio.wait_for(self.paypal.capture(order_id,token_urlsafe(24)),30)
                after=await asyncio.wait_for(self.paypal.get(order_id),30)
                if after.get('id')!=order_id or after.get('status')!='COMPLETED' or not self.matches(after,bound):
                    raise ClosedError('payee_mismatch')
                if captured.get('id')!=order_id or captured.get('status')!='COMPLETED' or not self.matches(captured,bound):
                    raise ClosedError('payee_mismatch')
                if self.capture_ids(captured)!=self.capture_ids(after):
                    raise ClosedError('capture_not_verified')
                bound.state='captured'
                return {'status':'captured','order_id':order_id,'observed_merchant':[bound.merchant]}
            except Exception:
                bound.state='manual_review'
                # Refund every known capture; never announce refund on ambiguity/failure.
                if captured:
                    try:
                        captures=[c['id'] for u in captured['purchase_units'] for c in u['payments']['captures']]
                        if not captures or any(not ID.fullmatch(c) for c in captures): raise ValueError()
                        for capture_id in sorted(set(captures)):
                            refund=await asyncio.wait_for(self.paypal.refund(capture_id,token_urlsafe(24)),30)
                            if refund.get('status')!='COMPLETED': raise ValueError()
                        bound.state='refunded'
                        raise ClosedError('capture_mismatch_refunded')
                    except ClosedError as error:
                        if str(error)=='capture_mismatch_refunded': raise
                    except Exception: pass
                raise ClosedError('capture_uncertain_manual_review') from None
