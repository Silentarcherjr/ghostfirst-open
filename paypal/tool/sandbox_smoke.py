"""Manual sandbox only. Default creates to human approval link, never captures."""
import argparse
import asyncio
import logging
from secrets import token_urlsafe
from ghost_checkout.config import runtime_config
from ghost_checkout.fixture import observe_corner
from ghost_checkout.api import RecordedGhost
from ghost_checkout.demo_data import BASE
from ghost_checkout.checkout import Checkout,BoundOrder
from ghost_checkout.evidence import ClosedError,ID
from ghost_checkout.sandbox import SandboxPayPal


async def run(action,order_id):
    config=runtime_config('sandbox')
    observation=await observe_corner(config)
    client=SandboxPayPal(config);owner=object()
    service=Checkout(RecordedGhost({BASE+'corner-bakery.html':observation}),client)
    merchant=observation['payment_provider']['merchant_ids'][0]
    if action=='create':
        result=await service.start_checkout(owner,BASE+'corner-bakery.html','Sandbox bakery smoke','1.00','USD')
        # These two values alone are explicitly authorized for the owner to approve.
        print(result['order_id'],flush=True)
        print(client.buyer_approval_url(result['order_id']),flush=True)
        return
    if not isinstance(order_id,str) or not ID.fullmatch(order_id): raise ClosedError('invalid_order')
    raw=await client.get(order_id)
    bound=BoundOrder(owner,merchant,'1.00','USD')
    if raw.get('id')!=order_id or not service.matches(raw,bound): raise ClosedError('payee_mismatch_before_capture')
    if action=='mismatch':
        wrong=BoundOrder(owner,'DELIBERATELY_DIFFERENT_EXPECTATION','1.00','USD')
        if service.matches(raw,wrong): raise ClosedError('mismatch_not_detected')
        print('PASS: mismatch rejected; no capture.',flush=True);return
    if raw.get('status')!='APPROVED': raise ClosedError('buyer_approval_required')
    service.orders[order_id]=bound
    result=await service.complete_checkout(owner,order_id)
    if result['status']!='captured': raise ClosedError('capture_not_verified')
    if action=='refund':
        after=await client.get(order_id)
        for capture in service.capture_ids(after):
            response=await client.refund(capture,token_urlsafe(24))
            if response.get('status')!='COMPLETED': raise ClosedError('refund_uncertain_manual_review')
        print('PASS: sandbox capture verified and refunded.',flush=True)
    else: print('PASS: sandbox capture and payee verified.',flush=True)


def main():
    logging.disable(logging.CRITICAL)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=['create','mismatch','capture','refund'],default='create')
    parser.add_argument('--order-id')
    args=parser.parse_args()
    try: asyncio.run(run(args.action,args.order_id))
    except BaseException:
        # No traceback, provider response, SDK object or secret is ever printed.
        print('FAIL: sandbox step stopped; no automatic retry.',flush=True)
        raise SystemExit(1) from None


if __name__=='__main__': main()
