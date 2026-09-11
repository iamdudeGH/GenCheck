"""GenCheck client — the fail-closed payment gate for shopping agents.

Everything here is the code path proven live in the benchmark runs and the
demo agent: cache reads via `get_cached_result`, full validation via
`validate_checkout` through real validator consensus, verdict decode from
the leader's on-chain eq_outputs.
"""

import base64
import json
import os
import time
from typing import Optional

from genlayer_py import create_account, create_client
from genlayer_py.chains import studio_devnet

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# get_transaction result names that mean "finished, no verdict coming" —
# anything else means consensus is still running.
_TERMINAL_RESULTS = {"FINISHED_WITH_ERROR", "REVERTED"}


def load_contract_address() -> str:
    """The final deployed contract (final_contract.json at repo root,
    overridable with GENCHECK_CONTRACT)."""
    return os.environ.get(
        "GENCHECK_CONTRACT",
        json.load(open(os.path.join(_ROOT, "final_contract.json")))["contract"])


def load_fees() -> dict:
    with open(os.path.join(_ROOT, "benchmark_fees.json")) as f:
        return json.load(f)


def extract_domain(url: str) -> str:
    if "://" in url:
        url = url.split("://", 1)[1]
    if "/" in url:
        url = url.split("/", 1)[0]
    if "@" in url:
        url = url.split("@", 1)[1]
    if ":" in url:
        url = url.split(":", 1)[0]
    return url.lower()


def retry(fn, tries=8, base_delay=15):
    """Retry transient RPC failures (Cloudflare challenges, JSON hiccups)."""
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
            time.sleep(base_delay * attempt)


class GenCheck:
    """The agent's trust layer: GenLayer validator consensus on checkout URLs.

    With a private key: full mode (can run consensus validations).
    Without: read-only mode (cache checks + registry lookups, free).
    """

    def __init__(self, private_key: Optional[str] = None):
        self.account = create_account(private_key) if private_key else create_account()
        self.client = create_client(chain=studio_devnet, account=self.account)
        self.contract = load_contract_address()
        self._fees = load_fees() if private_key else None

    # -- reads (free, instant) -------------------------------------------------

    def check_cache(self, domain: str) -> Optional[dict]:
        """Cached consensus verdict for a domain, or None if never validated."""
        try:
            return retry(lambda: self.client.read_contract(
                address=self.contract, function_name="get_cached_result",
                args=[domain]))
        except Exception:  # noqa: BLE001  (UserError = not yet validated)
            return None

    def official_domain(self, brand: str) -> str:
        """Registered official domain for a brand ('' if unregistered)."""
        return retry(lambda: self.client.read_contract(
            address=self.contract, function_name="get_official_domain",
            args=[brand]))

    # -- writes (real consensus) -----------------------------------------------

    def submit(self, checkout_url: str, brand: str) -> str:
        """Submit a validate_checkout transaction; returns the tx_id after
        ~2-5s, without waiting for consensus. Pair with poll() — designed for
        serverless hosts (Vercel) that kill long-running requests."""
        if self._fees is None:
            raise PermissionError(
                "GenCheck(private_key=...) is required to run validations")
        return retry(lambda: self.client.write_contract(
            address=self.contract, function_name="validate_checkout",
            args=[checkout_url, brand], account=self.account,
            fees={"distribution": self._fees["distribution"],
                  "feeValue": self._fees["paid_fee_value"]},
        ))

    def poll(self, tx_id: str, checkout_url: str = ""):
        """Non-blocking check of a submitted validation. Returns:
            dict      — consensus final, decoded verdict
            "pending" — consensus still running
            None      — finalized without a usable verdict (block by default)
        """
        tx = retry(lambda: self.client.get_transaction(tx_id))
        if tx.get("txExecutionResultName") != "FINISHED_WITH_RETURN":
            result = tx.get("txExecutionResultName")
            if result in _TERMINAL_RESULTS:  # finished, but badly
                return self._cache_fallback(checkout_url)
            return "pending"  # not finalized yet
        verdict = self.decode_verdict(tx_id)
        if verdict is None:
            # consensus returned but eq_output decode failed; fall back to cache
            return self._cache_fallback(checkout_url)
        return verdict

    def validate(self, checkout_url: str, brand: str) -> Optional[dict]:
        """Run full validator consensus on a checkout URL (blocking).

        Returns the verdict dict (is_real, verdict, confidence, reasons,
        evidence), or None if no verdict was produced (fetch failure beyond
        the contract's unverifiable handling, consensus timeout, tx error).
        The caller must treat None as BLOCK — see decide().
        """
        tx_id = self.submit(checkout_url, brand)
        for _ in range(150):  # ~12.5 min, matches the proven demo timings
            verdict = self.poll(tx_id, checkout_url)
            if verdict != "pending":
                return verdict
            time.sleep(5)
        return None

    def _cache_fallback(self, checkout_url: str) -> Optional[dict]:
        if not checkout_url:
            return None
        cached = self.check_cache(extract_domain(checkout_url))
        if cached is not None:
            return {"is_real": cached["is_real"],
                    "verdict": "real" if cached["is_real"] else "blocked",
                    "confidence": 100, "reasons": ["read from domain cache"],
                    "evidence": []}
        return None

    def decode_verdict(self, tx_id: str) -> Optional[dict]:
        """Full verdict (reasons, verdict, confidence) from the leader's
        on-chain eq_output; the cache only stores is_real."""
        tx = retry(lambda: self.client.get_transaction(tx_id))
        for receipt in tx["consensus_data"]["leader_receipt"]:
            for val in (receipt.get("eq_outputs") or {}).values():
                raw = val.get("raw", "")
                data = base64.b64decode(raw + "=" * (-len(raw) % 4))
                start = data.find(b"{")
                if start != -1:
                    try:
                        return json.loads(data[start:])
                    except json.JSONDecodeError:
                        continue
        return None


def decide(verdict: Optional[dict]) -> tuple:
    """The agent's pay/block policy. FAILS CLOSED: anything that is not an
    explicit consensus-backed `is_real: true` gets blocked.

    Returns ("PAY" | "BLOCK", reason).
    """
    if verdict is None:
        return "BLOCK", "no verdict — unverifiable, blocked by default"
    if verdict.get("is_real") is True:
        return "PAY", verdict.get("verdict", "real")
    return "BLOCK", verdict.get("verdict", "unknown")
