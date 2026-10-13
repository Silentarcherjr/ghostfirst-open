"""Immutable allowlisted evidence; page prose never crosses the model boundary."""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit
from .sensitive import one_time_link_indicators

ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
STATES = {'no_obvious_danger', 'caution', 'do_not_continue'}
TEXTS = {
    'page.paypal_checkout_seen': 'A PayPal checkout SDK request was observed.',
    'page.offsite_card_form': 'Card details were requested without an observed PayPal SDK.',
    'page.credentials_after_visual_change': 'The page changed into a credential form.',
    'page.payment_requested': 'Card details were requested.',
    'page.identifier_step': 'An identifier-only sign-in step was observed.',
    'domain.lookalike': 'The domain resembles a known brand.',
    'page.brand_domain_mismatch': 'A brand claim did not match the domain.',
    'scan.incomplete': 'The check did not complete.',
}


class ClosedError(Exception):
    """Fixed code only, never provider/page exception text."""


def store_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ClosedError('invalid_store_url')
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None,443):
            raise ValueError()
    except ValueError:
        raise ClosedError('invalid_store_url') from None
    if one_time_link_indicators(value):
        raise ClosedError('one_time_link_not_visited')
    return value


@dataclass(frozen=True)
class Check:
    verdict: str
    merchants: tuple[str, ...]
    claimed: str | None
    reasons: tuple[str, ...]
    rules: tuple[str, ...]

    def output(self):
        return {'status':'checked','verdict':self.verdict,
                'observed_merchant':list(self.merchants) or None,
                'reasons':[{'code':code,'text':TEXTS[code]} for code in self.reasons],
                'rules':list(self.rules), 'not_a_guarantee':True}


def sanitize(raw):
    try:
        if raw.get('status','complete') != 'complete' or not 200 <= raw['http_status'] < 300:
            raise ValueError()
        if raw.get('transport',{}).get('proxy_error'):
            raise ValueError()
        verdict = raw['verdict']['state']
        if verdict not in STATES: raise ValueError()
        provider = raw.get('payment_provider') or {}
        merchants = provider.get('merchant_ids', [])
        if not isinstance(merchants,list) or len(merchants)>20 or any(not isinstance(m,str) or not ID.fullmatch(m) for m in merchants):
            raise ValueError()
        if provider.get('provider') != 'paypal' or provider.get('sdk_seen') is not True:
            merchants=[]
        claimed = provider.get('claimed_merchant_id')
        if claimed is not None and (not isinstance(claimed,str) or not ID.fullmatch(claimed)): raise ValueError()
        reasons=tuple(sorted({f['code'] for f in raw['verdict'].get('findings',raw['verdict'].get('reasons',[])) if f.get('code') in TEXTS}))
        rules=tuple(r for r in raw['verdict'].get('rules',[]) if isinstance(r,str) and re.fullmatch(r'(CAU-(?:[0-9]|10)|DNC-[1-4]|NSB-0)',r))
        return Check(verdict,tuple(sorted(set(merchants))),claimed,reasons,rules)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ClosedError('check_failed') from None
