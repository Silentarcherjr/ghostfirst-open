"""Runtime-only external secrets, masked representations, no shell evaluation."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import stat
from pydantic import SecretStr
from .evidence import ClosedError, ID

PAYPAL_BASE='https://api-m.sandbox.paypal.com'
OPENROUTER_BASE='https://openrouter.ai/api/v1'


@dataclass(frozen=True)
class SandboxConfig:
    client_id: SecretStr
    client_secret: SecretStr
    merchant_id: SecretStr
    llm_key: SecretStr
    llm_model: str
    webhook_id: SecretStr = field(default_factory=lambda:SecretStr(''))
    paypal_base: str = PAYPAL_BASE
    llm_base: str = OPENROUTER_BASE

    def __post_init__(self):
        if self.paypal_base!=PAYPAL_BASE or self.llm_base!=OPENROUTER_BASE:
            raise ClosedError('sandbox_configuration_required')
        if not ID.fullmatch(self.merchant_id.get_secret_value()) or not ID.fullmatch(self.client_id.get_secret_value()): raise ClosedError('invalid_credentials_file')

    def redact(self,text):
        for secret in (self.client_id,self.client_secret,self.merchant_id,self.llm_key,self.webhook_id):
            value=secret.get_secret_value()
            if value: text=text.replace(value,'[REDACTED]')
        return text


def runtime_config(mode=None,path=None):
    mode=mode or os.environ.get('GHOST_CHECKOUT_MODE','offline')
    if mode=='offline': return None # Never even stat/read the file in default mode.
    if mode!='sandbox': raise ClosedError('sandbox_configuration_required')
    path=Path(path or os.environ.get('GHOST_CHECKOUT_SECRETS','~/.config/ghostfirst/paypal.env')).expanduser()
    try:
        # Secrets must be outside this repository, regular, owned, mode 0600.
        repo=Path(__file__).resolve().parents[4]
        if path.resolve().is_relative_to(repo): raise ValueError()
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd) as source:
            meta=os.fstat(source.fileno())
            if not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode)!=0o600 or meta.st_uid!=os.getuid(): raise ValueError()
            values={}
            for line in source:
                if not line.strip() or line.lstrip().startswith('#'): continue
                key,separator,value=line.partition('=')
                key=key.strip().removeprefix('export ')
                if not separator or key in values: raise ValueError()
                parsed=shlex.split(value,comments=True)
                if len(parsed)>1: raise ValueError()
                values[key]=parsed[0] if parsed else ''
        for key in ('PAYPAL_ENVIRONMENT','PAYPAL_MODE','GHOST_CHECKOUT_MODE'):
            if values.get(key,'sandbox')!='sandbox' or os.environ.get(key,'sandbox')!='sandbox': raise ValueError()
        for key in ('PAYPAL_BASE_URL','PAYPAL_API_BASE'):
            if values.get(key,PAYPAL_BASE)!=PAYPAL_BASE or os.environ.get(key,PAYPAL_BASE)!=PAYPAL_BASE: raise ValueError()
        for key in ('PAYPAL_CLIENT_ID','PAYPAL_CLIENT_SECRET','SANDBOX_MERCHANT_ID','LLM_API_KEY','LLM_MODEL'):
            if not values.get(key): raise ValueError()
        return SandboxConfig(SecretStr(values['PAYPAL_CLIENT_ID']),SecretStr(values['PAYPAL_CLIENT_SECRET']),
            SecretStr(values['SANDBOX_MERCHANT_ID']),SecretStr(values['LLM_API_KEY']),values['LLM_MODEL'],
            SecretStr(values.get('PAYPAL_WEBHOOK_ID','')),llm_base=values.get('LLM_BASE_URL',OPENROUTER_BASE))
    except Exception:
        raise ClosedError('invalid_sandbox_configuration') from None
