"""GenCheck MCP server — add scam-proof checkout validation to any AI agent.

Exposes the deployed GenCheck intelligent contract (GenLayer studio-dev) as
Model Context Protocol tools, so MCP-capable agents (Claude Code, Claude
Desktop, Cursor, custom agent frameworks) can gate payments on decentralized
validator consensus with zero integration code.

Tools:
    gencheck_check_domain(domain)        cached verdict (free read, no tx)
    gencheck_validate(url, brand)        real consensus transaction (~0.00008 GEN)
    gencheck_official_domain(brand)      brand registry lookup

Reads work with no configuration. gencheck_validate needs
GENCHECK_PRIVATE_KEY (funded account — each call is a real transaction).

Run (stdio transport, the standard for local MCP servers):
    gencheck-mcp                    # console script, after `pip install gencheck`
    python -m gencheck.mcp_server   # equivalent, without the console script

Register with Claude Code:
    claude mcp add gencheck --env GENCHECK_PRIVATE_KEY=0x... -- gencheck-mcp
"""

import json
import os

from mcp.server.mcpserver import MCPServer

from .client import GenCheck, decide

mcp = MCPServer("gencheck")

def _env_private_key() -> str | None:
    """GENCHECK_PRIVATE_KEY, treating an unexpanded placeholder as unset.

    The Claude Code plugin passes the key through its `.mcp.json` as
    `${user_config.private_key}`. If that substitution ever fails, the literal
    string lands in the environment and `create_account()` raises something
    opaque instead of saying the key is missing. Treating a residual `${...}`
    as "no key" means the server simply runs read-only, and
    `gencheck_validate` returns its normal explanatory error.
    """
    value = os.environ.get("GENCHECK_PRIVATE_KEY")
    if not value or (value.startswith("${") and value.endswith("}")):
        return None
    return value


_private_key = _env_private_key()
# read-only until a validation is first requested with a key present
_gc: GenCheck | None = None
_gc_full: GenCheck | None = None


def _readonly() -> GenCheck:
    global _gc
    if _gc is None:
        _gc = GenCheck()
    return _gc


def _full() -> GenCheck:
    global _gc_full
    if not _private_key:
        raise RuntimeError(
            "gencheck_validate requires GENCHECK_PRIVATE_KEY "
            "(funded account — each validation is a real transaction costing "
            "~0.00008 GEN). Cache checks via gencheck_check_domain are free.")
    if _gc_full is None:
        _gc_full = GenCheck(private_key=_private_key)
    return _gc_full


@mcp.tool()
def gencheck_check_domain(domain: str) -> str:
    """Check if a checkout domain was already validated by GenCheck validator
    consensus. Free and instant (reads the on-chain domain cache).

    Returns the cached verdict: is_real true means the domain was cleared as
    a real seller; false means it was blocked (scam / wrong_seller /
    unverifiable). A domain with no cached verdict has never been validated —
    use gencheck_validate for a full consensus run.
    """
    cached = _readonly().check_cache(domain.strip().lower())
    if cached is None:
        return json.dumps({
            "domain": domain, "status": "never_validated",
            "decision": "BLOCK",
            "hint": "no consensus verdict on chain yet — run gencheck_validate",
        })
    action, why = decide({"is_real": cached["is_real"]})
    return json.dumps({
        "domain": domain, "status": "cached_consensus_verdict",
        "is_real": cached["is_real"], "decision": action, "reason": why,
    })


@mcp.tool()
def gencheck_validate(checkout_url: str, brand: str) -> str:
    """Validate a checkout URL through full GenLayer validator consensus
    (a real transaction, ~0.00008 GEN; the contract returns its cached verdict
    quickly for a domain judged before, but the transaction is real either way).

    Validators fetch the checkout page AND the claimed brand's official site,
    then vote on one question: is this the brand's real seller or a
    lookalike/wrong-brand scam? FAILS CLOSED: pay only if is_real is true;
    scam / wrong_seller / unsure / unverifiable / no-verdict all mean BLOCK.
    """
    verdict = None
    error = None
    try:
        verdict = _full().validate(checkout_url.strip(), brand.strip().lower())
    except RuntimeError as e:  # no key configured — fail closed, tell the agent why
        error = str(e)
    action, why = decide(verdict)
    if error is not None:
        return json.dumps({
            "checkout_url": checkout_url, "brand": brand,
            "status": "error", "decision": "BLOCK",
            "reason": error,
            "hint": "no verdict obtained — do not pay",
        })
    if verdict is None:
        return json.dumps({
            "checkout_url": checkout_url, "brand": brand,
            "status": "no_verdict", "decision": "BLOCK",
            "reason": why,
            "hint": "validators could not produce a verdict — do not pay",
        })
    conf = verdict.get("confidence")
    if isinstance(conf, float) and conf <= 1.0:  # raw LLM scale 0-1
        conf = int(round(conf * 100))
    return json.dumps({
        "checkout_url": checkout_url, "brand": brand,
        "status": "consensus_verdict",
        "is_real": verdict.get("is_real"),
        "verdict": verdict.get("verdict"),
        "confidence": conf,
        "reasons": verdict.get("reasons", [])[:4],
        "decision": action, "decision_reason": why,
    })


@mcp.tool()
def gencheck_official_domain(brand: str) -> str:
    """Look up the registered official domain for a brand in GenCheck's
    on-chain registry (e.g. 'apple' -> 'apple.com'). Empty string if the
    brand is not registered — validation then falls back to the validators'
    general knowledge of the brand.
    """
    domain = _readonly().official_domain(brand.strip().lower())
    return json.dumps({
        "brand": brand,
        "official_domain": domain or None,
        "registered": bool(domain),
    })


def main() -> None:
    """Console-script entry point (`gencheck-mcp`) and `python -m` target."""
    mcp.run()


if __name__ == "__main__":
    main()
