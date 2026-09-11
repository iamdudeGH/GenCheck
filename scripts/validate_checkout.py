"""Submit a validate_checkout write to the deployed GenCheck contract on studio-dev.

Requires the dedicated venv (genlayer-py 0.19.0rc2 — the Consensus v0.6 RC SDK):

    .venv-deploy/Scripts/pip install --pre "genlayer-py==0.19.0rc2"

Usage:
    set GENCHECK_PRIVATE_KEY=0x...          (funded burner key)
    .venv-deploy/Scripts/python scripts/validate_checkout.py <checkout_url> <brand>

Flow: estimate fees (write simulation) -> submit with fees -> wait for finalization
-> verify execution result -> read back the cached verdict.
"""

import json
import os
import sys

from genlayer_py import create_account, create_client
from genlayer_py.chains import studio_devnet
from genlayer_py.transactions import is_successful


def contract_address():
    with open(os.path.join(os.path.dirname(__file__), "..", "final_contract.json")) as f:
        return json.load(f)["contract"]


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    checkout_url, brand = sys.argv[1], sys.argv[2]

    private_key = os.environ.get("GENCHECK_PRIVATE_KEY")
    if not private_key:
        print("Set GENCHECK_PRIVATE_KEY to a funded account's private key")
        sys.exit(1)

    account = create_account(private_key)
    print(f"account: {account.address}")
    client = create_client(chain=studio_devnet, account=account)

    print(f"\n1. estimating fees for validate_checkout({checkout_url!r}, {brand!r}) ...")
    estimate = client.estimate_transaction_fees_for_write(
        address=contract_address(),
        function_name="validate_checkout",
        args=[checkout_url, brand],
        account=account,
    )
    fee_value = estimate["feeValue"]
    print(f"   fee value: {fee_value}")

    print("\n2. submitting transaction ...")
    tx_id = client.write_contract(
        address=contract_address(),
        function_name="validate_checkout",
        args=[checkout_url, brand],
        account=account,
        fees={"distribution": estimate["distribution"], "feeValue": fee_value},
    )
    print(f"   tx id: {tx_id}")

    print("\n3. waiting for finalization (web fetch + LLM + consensus) ...")
    receipt = client.wait_for_finalization(tx_id, retries=120, interval=5000)
    print(f"   result: {receipt.get('result_name')}")
    print(f"   execution: {receipt.get('txExecutionResultName')}")
    if not is_successful(receipt):
        print(f"\n   TRANSACTION FAILED: {receipt.get('result_name')} / "
              f"{receipt.get('txExecutionResultName')}")
        sys.exit(2)

    print("\n4. reading back the cached verdict ...")
    domain = checkout_url.split("://", 1)[-1].split("/", 1)[0].lower()
    validated = client.read_contract(
        address=contract_address(),
        function_name="is_site_validated",
        args=[domain],
    )
    cached = client.read_contract(
        address=contract_address(),
        function_name="get_cached_result",
        args=[domain],
    )
    print(f"   is_site_validated({domain!r}) = {validated}")
    print(f"   cached result = {cached}")

    if cached.get("is_real"):
        print("\n   VERDICT: REAL - allow pay [OK]")
    else:
        print("\n   VERDICT: NOT REAL - block pay [BLOCKED]")


if __name__ == "__main__":
    main()
