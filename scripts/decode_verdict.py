"""Decode the leader's verdict from a tx receipt.

Two receipt shapes exist and this prints whichever the tx carries:

    result.payload.readable   the runtime's own decoded JSON string — present
                              on every round we have seen, old and new
    eq_outputs                base64 blob with the JSON embedded — older rounds
                              only; EMPTY on rounds run after the ~12 Sept
                              network change

Kept raw on purpose: when a verdict fails to decode, this is the script that
shows what the chain actually returned.

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
    if receipt.get("mode") != "leader":
        continue

    payload = (receipt.get("result") or {}).get("payload") or {}
    readable = payload.get("readable")
    if isinstance(readable, str):
        print(f"[payload.readable] {readable}")

    eq = receipt.get("eq_outputs") or {}
    if not eq:
        print("[eq_outputs] (empty on this round)")
    for key, val in eq.items():
        raw = val.get("raw", "")
        data = base64.b64decode(raw + "=" * (-len(raw) % 4))
        # eq output format: short binary header, then the JSON payload
        start = data.find(b"{")
        if start == -1:
            print(f"[eq:{key}] (no JSON payload) {data[:100]!r}")
            continue
        print(f"[eq:{key}] {data[start:].decode('utf-8', 'replace')}")
