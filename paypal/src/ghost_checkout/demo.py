"""Offline runner; deliberately no credential loading or cloud provisioning."""
import argparse
import os
from .evidence import ClosedError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',choices=['127.0.0.1','0.0.0.0'],default='127.0.0.1',help='0.0.0.0 only for a private Codespaces port forward')
    parser.add_argument('--port',type=int,default=8876)
    args=parser.parse_args()
    mode=os.environ.get('GHOST_CHECKOUT_MODE','offline')
    if mode not in {'offline','sandbox'}: raise SystemExit('Only offline or PayPal sandbox mode is allowed.')
    if not 1024<=args.port<=65535: parser.error('Use a nonprivileged port.')
    import uvicorn
    target='ghost_checkout.web:create_sandbox_app' if mode=='sandbox' else 'ghost_checkout.web:create_app'
    if mode=='sandbox' and args.host!='127.0.0.1': raise SystemExit('Sandbox mode is loopback only before review.')
    uvicorn.run(target,factory=True,host=args.host,port=args.port,access_log=False)


if __name__ == '__main__':
    main()
