"""Decode the leader's eq_output (the raw LLM verdict JSON) from a tx.

Usage:
    .venv-deploy/Scripts/python scripts/decode_verdict.py <tx_hash>
"""

import base64
import sys

from genlayer_py import create_account, create_client
from genlayer_py.chains import studio_devnet

tx_hash = sys.argv[1]
client = create_client(chain=studio_devnet, account=create_account())
tx = client.get_transaction(tx_hash)

for receipt in tx["consensus_data"]["leader_receipt"]:
    eq = receipt.get("eq_outputs") or {}
    for key, val in eq.items():
        raw = val.get("raw", "")
        pad = "=" * (-len(raw) % 4)
        data = base64.b64decode(raw + pad)
        # eq output format: short binary header, then the JSON payload
        start = data.find(b"{")
        if start == -1:
            print(f"[{key}] (no JSON payload) {data[:100]!r}")
            continue
        print(f"[{key}] {data[start:].decode('utf-8', 'replace')}")
