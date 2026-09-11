"""Interact with the deployed GenCheck contract on studio-dev.

Reads are unsigned — a throwaway account is generated for the `from` field.

Usage (from project root):
    python scripts/interact.py                       # status reads
    python scripts/interact.py --check apple.com     # cached verdict for a domain

Network: studio-dev preview (chain ID 61997, Agent Tank network)
RPC: https://studio-dev.genlayer.com/api
Explorer: https://explorer-studio-dev.genlayer.com
"""

import argparse

from genlayer_py import create_account, create_client

CONTRACT_ADDRESS = "0x59c1236654579e98154bF5806edE44a745D6b5F3"
RPC_ENDPOINT = "https://studio-dev.genlayer.com/api"


def get_client():
    account = create_account()  # ephemeral; reads are not signed
    return create_client(endpoint=RPC_ENDPOINT, account=account)


def main():
    parser = argparse.ArgumentParser(description="GenCheck studio-dev client")
    parser.add_argument(
        "--check", metavar="DOMAIN",
        help="show the cached verdict for a domain",
    )
    parser.add_argument(
        "--brand", metavar="NAME",
        help="look up the registered official domain for a brand",
    )
    args = parser.parse_args()

    client = get_client()

    if args.check:
        validated = client.read_contract(
            address=CONTRACT_ADDRESS,
            function_name="is_site_validated",
            args=[args.check],
        )
        print(f"is_site_validated({args.check!r}) = {validated}")
        if validated:
            cached = client.read_contract(
                address=CONTRACT_ADDRESS,
                function_name="get_cached_result",
                args=[args.check],
            )
            print(f"get_cached_result({args.check!r}) = {cached}")
        return

    if args.brand:
        domain = client.read_contract(
            address=CONTRACT_ADDRESS,
            function_name="get_official_domain",
            args=[args.brand],
        )
        print(f"get_official_domain({args.brand!r}) = {domain!r}")
        return

    # default: status summary
    print(f"GenCheck @ {CONTRACT_ADDRESS} (studio-dev, chain 61997)")
    for brand in ["apple", "amazon", "paypal", "microsoft"]:
        domain = client.read_contract(
            address=CONTRACT_ADDRESS,
            function_name="get_official_domain",
            args=[brand],
        )
        print(f"  registry: {brand:<10} -> {domain}")


if __name__ == "__main__":
    main()
