"""Dump the raw shape of one benchmark tx to find where the target address lives."""

import json

from genlayer_py import create_account, create_client
from genlayer_py.chains import studio_devnet

client = create_client(chain=studio_devnet, account=create_account())
tx = client.get_transaction(
    "0xdd90af9f946d2c2cd0d82d1c49299ebf1c13b51953056a19c6640f1a072e6921")


def shape(o, depth=0):
    if depth > 3:
        return repr(o)[:80]
    if isinstance(o, dict):
        return {k: shape(v, depth + 1) for k, v in o.items()}
    if isinstance(o, list):
        return [shape(o[0], depth + 1)] if o else []
    return repr(o)[:80]


print(json.dumps(shape(tx), indent=1, default=str))
