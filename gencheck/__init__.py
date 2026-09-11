"""GenCheck — a shopping agent's trust layer for checkout URLs.

Client package shared by the demo agent and the MCP server. Wraps the
deployed GenCheck intelligent contract on studio-dev:

    from gencheck import GenCheck

    gc = GenCheck(private_key=os.environ["GENCHECK_PRIVATE_KEY"])  # writes
    gc = GenCheck()                                                # reads only

    cached = gc.check_cache("www.amazon.com")   # free read, None if unvalidated
    verdict = gc.validate(url, brand)           # real consensus transaction
    action, why = gc.decide(verdict)            # ("PAY"|"BLOCK", reason) — fails closed
"""

from .client import GenCheck, decide, load_contract_address

__all__ = ["GenCheck", "decide", "load_contract_address"]
