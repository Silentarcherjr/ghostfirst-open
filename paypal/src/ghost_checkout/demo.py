"""Offline runner; deliberately no credential loading or cloud provisioning."""
import argparse
import os
from .evidence import ClosedError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',choices=['127.0.0.1','0.0.0.0'],default='127.0.0.1',help='0.0.0.0 only for a private Codespaces port forward')
    parser.add_argument('--port',type=int,default=8876)
    args=parser.parse_args()
    if os.environ.get('GHOST_CHECKOUT_MODE','offline')!='offline':
        raise SystemExit('Real provider modes are disabled until E6 review and authorization.')
    if not 1024<=args.port<=65535: parser.error('Use a nonprivileged port.')
    import uvicorn
    uvicorn.run('ghost_checkout.web:app',host=args.host,port=args.port,access_log=False)


if __name__ == '__main__':
    main()
