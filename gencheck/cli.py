"""GenCheck CLI — the gate for agents that do not speak MCP.

An MCP server only reaches agents that implement MCP. A command reaches every
agent that can start a process, which is all of them. The contract is the exit
code, so a shell chain fails closed with no glue at all:

    gencheck check "$CHECKOUT_URL" "$BRAND" && pay || refuse

    0  PAY    consensus returned is_real: true
    1  BLOCK  consensus returned a verdict, and it was not is_real: true
    2  ERROR  no verdict obtained — no key, network failure, unverifiable

stdout is a single JSON object, so a caller that would rather parse than check
exit codes can do that instead.

    gencheck check https://shop.example/checkout example   real tx, needs a key
    gencheck cache shop.example                            free read, no key
    gencheck domain example                                free read, no key

The key is the agent's OWN funded studio-dev account, taken from
GENCHECK_PRIVATE_KEY or --private-key. Every `check` spends that account's GEN
(~0.00008 per validation) and never anyone else's. Fund it from the studio-dev
faucet.
"""

import argparse
import json
import os
import sys

from .client import GenCheck, decide, extract_domain

EXIT_PAY, EXIT_BLOCK, EXIT_ERROR = 0, 1, 2


def _emit(payload: dict, code: int) -> int:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return code


def _confidence(verdict: dict):
    conf = verdict.get("confidence")
    if isinstance(conf, float) and conf <= 1.0:  # raw LLM 0-1 scale
        conf = int(round(conf * 100))
    return conf


def cmd_cache(args) -> int:
    domain = extract_domain(args.domain)
    cached = GenCheck().check_cache(domain)
    if cached is None:
        action, why = decide(None)
        return _emit({"domain": domain, "status": "never_validated",
                      "is_real": None, "decision": action, "reason": why},
                     EXIT_BLOCK)
    action, why = decide({"is_real": cached["is_real"]})
    return _emit({"domain": domain, "status": "cached_consensus_verdict",
                  "is_real": cached["is_real"], "decision": action,
                  "reason": why},
                 EXIT_PAY if action == "PAY" else EXIT_BLOCK)


def cmd_domain(args) -> int:
    brand = args.brand.strip().lower()
    domain = GenCheck().official_domain(brand)
    return _emit({"brand": brand, "official_domain": domain or None,
                  "registered": bool(domain)}, EXIT_PAY)


def cmd_check(args) -> int:
    key = args.private_key or os.environ.get("GENCHECK_PRIVATE_KEY")
    if not key:
        action, why = decide(None)
        return _emit({
            "url": args.url, "brand": args.brand, "status": "error",
            "is_real": None, "decision": action, "reason": why,
            "hint": ("GENCHECK_PRIVATE_KEY is not set. `check` submits a real "
                     "transaction, so it needs a funded studio-dev account of "
                     "your own — get one from the faucet, then set the var. "
                     "`gencheck cache <domain>` is free and needs no key."),
        }, EXIT_ERROR)
    try:
        verdict = GenCheck(private_key=key).validate(args.url, args.brand.lower())
    except Exception as e:  # noqa: BLE001 — an error must never read as an allow
        action, why = decide(None)
        return _emit({"url": args.url, "brand": args.brand, "status": "error",
                      "is_real": None, "decision": action,
                      "reason": f"validation failed: {e}"}, EXIT_ERROR)
    if verdict is None:
        action, why = decide(None)
        return _emit({"url": args.url, "brand": args.brand,
                      "status": "no_verdict", "is_real": None,
                      "decision": action, "reason": why}, EXIT_ERROR)
    action, why = decide(verdict)
    return _emit({
        "url": args.url, "brand": args.brand, "status": "consensus_verdict",
        "is_real": verdict.get("is_real"), "verdict": verdict.get("verdict"),
        "confidence": _confidence(verdict),
        "reasons": (verdict.get("reasons") or [])[:4],
        "decision": action, "decision_reason": why,
    }, EXIT_PAY if action == "PAY" else EXIT_BLOCK)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="gencheck",
        description="Verify a seller before your agent pays it. Fails closed: "
                    "exit 0 only on an explicit consensus is_real: true.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="full validator consensus (real tx; needs a key)")
    c.add_argument("url")
    c.add_argument("brand")
    c.add_argument("--private-key",
                   help="funded studio-dev key (else GENCHECK_PRIVATE_KEY)")
    c.set_defaults(fn=cmd_check)

    k = sub.add_parser("cache", help="cached verdict for a domain (free read, no key)")
    k.add_argument("domain")
    k.set_defaults(fn=cmd_cache)

    d = sub.add_parser("domain", help="official domain for a brand (free read, no key)")
    d.add_argument("brand")
    d.set_defaults(fn=cmd_domain)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
