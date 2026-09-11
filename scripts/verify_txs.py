"""Verify benchmark transactions on-chain: fetch each recorded tx id and print
its target contract, consensus status, and execution result.

Usage:
    .venv-deploy/Scripts/python scripts/verify_txs.py
"""

import glob
import json

from genlayer_py import create_account, create_client
from genlayer_py.chains import studio_devnet

BENCHMARK_CONTRACT = "0x04a9cCB5Cd21D36d5345577dcEE3CEDE19A0917d"


def retry(fn, tries=8, base_delay=15):
    import time as _t
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            transient = ("invalid JSON" in msg or "DOCTYPE" in msg
                         or "1010" in msg or "Timeout" in msg
                         or "timed out" in msg.lower())
            if attempt == tries or not transient:
                raise
            _t.sleep(base_delay * attempt)


def main():
    client = create_client(chain=studio_devnet, account=create_account())

    # collect every recorded tx id from all benchmark result files
    txs = {}  # tx_id -> (url, brand)
    for path in glob.glob("benchmark_*.json"):
        if path == "benchmark_fees.json":
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # result files are either {"contract":..., "cases":[...]} or a bare list
        if isinstance(data, list):
            cases = data
        elif isinstance(data, dict):
            cases = data.get("cases", [])
        else:
            cases = []
        for c in cases:
            if isinstance(c, dict) and c.get("tx_id"):
                txs[c["tx_id"]] = (c.get("url", "?"), c.get("brand", "?"))

    print(f"recorded tx ids: {len(txs)}\n")
    print(f"{'tx':<20} {'to==bench':<10} {'result_name':<18} "
          f"{'execution':<24} case")
    print("-" * 100)

    to_contract = 0
    for tx_id, (url, brand) in txs.items():
        try:
            tx = retry(lambda: client.get_transaction(tx_id))
            # the rich tx view names it to_address
            to_addr = tx.get("to_address") or tx.get("to") or ""
            # explorer checksums differ; compare case-insensitively
            match = to_addr.lower() == BENCHMARK_CONTRACT.lower()
            to_contract += bool(match)
            result_name = tx.get("result_name", "?")
            execution = tx.get("txExecutionResultName", "?")
            print(f"{tx_id[:18]}... {str(match):<10} {str(result_name):<18} "
                  f"{str(execution):<24} {url} [{brand}] to={to_addr}")
        except Exception as e:  # noqa: BLE001
            print(f"{tx_id[:18]}... ERROR {str(e)[:120]}")

    print("-" * 100)
    print(f"total: {len(txs)} txs, {to_contract} addressed to the "
          f"benchmark contract")


if __name__ == "__main__":
    main()
