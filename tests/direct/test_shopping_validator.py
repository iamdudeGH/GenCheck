"""Direct tests for GenCheck ShoppingValidator contract.

Uses the gltest direct-mode harness: real SDK in-memory execution with
mocked web and LLM calls. Run from the project root:

    pytest tests/direct/ -v

Notes on mocking:
- vm.mock_web(url_pattern, {"body": ...})    — regex-searched against the URL;
  for web.render the body becomes the rendered text.
- vm.mock_llm(prompt_pattern, response)      — regex-searched against the prompt.
  Responses are fenced JSON (like real LLM output) so exec_prompt keeps
  returning a str; the direct-mode mock layer auto-parses bare JSON into dicts.
- prompt_comparative runs the leader closure directly in direct mode and
  returns its result (the EqComparative validator side needs a simulator —
  that's covered by integration tests).
"""

import json

import pytest

CONTRACT = "contracts/shopping_validator.py"


# --- Helpers ---------------------------------------------------------------

def llm_verdict(is_real: bool, confidence: float, verdict: str) -> str:
    """Build a fenced-JSON LLM response like real models produce."""
    payload = json.dumps({
        "is_real": is_real,
        "confidence": confidence,
        "reasons": ["domain analysis", "page branding"],
        "evidence": ["https://example.com"],
        "verdict": verdict,
    })
    return f"```json\n{payload}\n```"


def mock_brand_pages(vm, checkout_body: str, official_body: str = "Official brand homepage"):
    """Register web mocks for a checkout URL and its official brand page."""
    vm.mock_web(r"example-shop\.com/checkout", {"body": checkout_body})
    vm.mock_web(r"^https://apple\.com$", {"body": official_body})


# --- Validation flow -------------------------------------------------------

def test_validate_real_site(direct_vm, direct_deploy):
    """A legitimate checkout URL is validated as real."""
    mock_brand_pages(direct_vm, "Apple Store checkout with Apple Pay")
    direct_vm.mock_llm(r"security expert validating", llm_verdict(True, 0.95, "real"))

    contract = direct_deploy(CONTRACT)
    result = contract.validate_checkout("https://example-shop.com/checkout", "apple")

    assert result["is_real"] is True
    assert result["verdict"] == "real"
    assert result["confidence"] == 95


def test_validate_lookalike_scam(direct_vm, direct_deploy):
    """A lookalike checkout page is flagged as a scam."""
    mock_brand_pages(direct_vm, "Suspicious Appl3 Store checkout")
    direct_vm.mock_llm(r"security expert validating", llm_verdict(False, 0.95, "scam"))

    contract = direct_deploy(CONTRACT)
    result = contract.validate_checkout("https://example-shop.com/checkout", "apple")

    assert result["is_real"] is False
    assert result["verdict"] == "scam"


def test_wrong_seller_is_blocked(direct_vm, direct_deploy):
    """A legitimate but wrong-brand site (v2 prompt: rule 2) is blocked.

    This is the case the v1 benchmark missed: walmart.com is a real, safe
    checkout — just not Amazon's. The v2 prompt's domain-ownership criterion
    must return is_real=False with verdict "wrong_seller".
    """
    mock_brand_pages(direct_vm, "Walmart checkout - pay with Walmart Pay")
    direct_vm.mock_llm(
        r"security expert validating", llm_verdict(False, 0.9, "wrong_seller"))

    contract = direct_deploy(CONTRACT)
    result = contract.validate_checkout("https://example-shop.com/checkout", "amazon")

    assert result["is_real"] is False
    assert result["verdict"] == "wrong_seller"
    # and the block is cached like any other not-real verdict
    assert contract.is_site_validated("example-shop.com") is False


def test_validate_unknown_brand_skips_official_fetch(direct_vm, direct_deploy):
    """A brand not in the registry still validates — with only one web call."""
    direct_vm.mock_web(r"example-shop\.com/checkout", {"body": "Some checkout page"})
    direct_vm.mock_llm(r"security expert validating", llm_verdict(True, 0.80, "real"))

    contract = direct_deploy(CONTRACT)
    result = contract.validate_checkout("https://example-shop.com/checkout", "mysterybrand")

    assert result["is_real"] is True
    # Only the checkout URL mock was registered; the official-page fetch would
    # have raised MockNotFoundError if attempted for an unregistered brand.
    assert contract.get_official_domain("mysterybrand") == ""


def test_low_confidence_scam_still_blocks(direct_vm, direct_deploy):
    """A scam verdict with low confidence is still cached as not real."""
    mock_brand_pages(direct_vm, "Suspicious checkout page")
    direct_vm.mock_llm(r"security expert validating", llm_verdict(False, 0.55, "scam"))

    contract = direct_deploy(CONTRACT)
    result = contract.validate_checkout("https://example-shop.com/checkout", "apple")

    assert result["is_real"] is False
    assert result["verdict"] == "scam"


# --- Caching ---------------------------------------------------------------

def test_cached_result_skips_web_and_llm(direct_vm, direct_deploy):
    """Second validation of the same domain returns the cached verdict
    without hitting web or LLM again."""
    mock_brand_pages(direct_vm, "Apple Store checkout")
    direct_vm.mock_llm(r"security expert validating", llm_verdict(True, 0.90, "real"))

    contract = direct_deploy(CONTRACT)

    result1 = contract.validate_checkout("https://example-shop.com/checkout", "apple")
    assert result1["is_real"] is True

    # Clear all mocks: a re-validation would now fail if it hit web/LLM again
    direct_vm.clear_mocks()

    result2 = contract.validate_checkout("https://example-shop.com/checkout", "apple")
    assert result2["is_real"] is True
    assert result2["confidence"] == 100
    assert "cached" in result2["reasons"][0]
    assert result2["verdict"] == "real"


def test_scam_verdict_is_cached_as_blocked(direct_vm, direct_deploy):
    """A scam verdict is cached so repeat checks stay blocked for free."""
    mock_brand_pages(direct_vm, "Suspicious checkout page")
    direct_vm.mock_llm(r"security expert validating", llm_verdict(False, 0.90, "scam"))

    contract = direct_deploy(CONTRACT)
    contract.validate_checkout("https://example-shop.com/checkout", "apple")

    direct_vm.clear_mocks()

    result = contract.validate_checkout("https://example-shop.com/checkout", "apple")
    assert result["is_real"] is False
    assert result["verdict"] == "scam"
    assert result["confidence"] == 100


def test_domain_scoped_caching(direct_vm, direct_deploy):
    """A verdict for one domain never leaks to a lookalike domain."""
    contract = direct_deploy(CONTRACT)
    contract.add_official_domain("goodshop", "goodshop.com")

    direct_vm.mock_web(r"^https://goodshop\.com/checkout$", {"body": "Good checkout"})
    direct_vm.mock_web(r"^https://goodshop\.com$", {"body": "Official page"})
    direct_vm.mock_llm(r"security expert validating", llm_verdict(True, 0.95, "real"))

    contract.validate_checkout("https://goodshop.com/checkout", "goodshop")

    assert contract.is_site_validated("goodshop.com") is True
    assert contract.is_site_validated("goodshop.com.evil.io") is False
    assert contract.is_site_validated("evil.io") is False


# --- View methods ----------------------------------------------------------

def test_is_site_validated_default_false(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    assert contract.is_site_validated("never-validated.com") is False


def test_get_cached_result_unvalidated_raises(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    with pytest.raises(Exception):
        contract.get_cached_result("never-validated.com")


def test_get_cached_result_after_validation(direct_vm, direct_deploy):
    mock_brand_pages(direct_vm, "Apple Store checkout")
    direct_vm.mock_llm(r"security expert validating", llm_verdict(True, 0.90, "real"))

    contract = direct_deploy(CONTRACT)
    contract.validate_checkout("https://example-shop.com/checkout", "apple")

    cached = contract.get_cached_result("example-shop.com")
    assert cached["domain"] == "example-shop.com"
    assert cached["is_real"] is True


# --- Brand registry --------------------------------------------------------

def test_seeded_brands_present(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT)
    assert contract.get_official_domain("apple") == "apple.com"
    assert contract.get_official_domain("amazon") == "amazon.com"
    assert contract.get_official_domain("paypal") == "paypal.com"


def test_add_official_domain_persists(direct_vm, direct_deploy):
    """Registered domains live in contract storage, not a module global."""
    contract = direct_deploy(CONTRACT)
    contract.add_official_domain("newbrand", "newbrand.com")
    assert contract.get_official_domain("newbrand") == "newbrand.com"
    # brand lookup is case-insensitive
    contract.add_official_domain("MixedCase", "mixed.com")
    assert contract.get_official_domain("mixedcase") == "mixed.com"


def test_domain_extraction_variants(direct_vm, direct_deploy):
    """The contract's URL parser handles scheme, port, userinfo, and case."""
    # (?i): the URL keeps its original case; only the cache key is normalized
    direct_vm.mock_web(r"(?i)shop\.example\.com", {"body": "checkout"})
    direct_vm.mock_web(r"^https://apple\.com$", {"body": "Apple official page"})
    direct_vm.mock_llm(r"security expert validating", llm_verdict(True, 0.9, "real"))

    contract = direct_deploy(CONTRACT)
    # All of these normalize to the same domain -> second call is cached
    contract.validate_checkout("https://Shop.example.com:443/checkout", "apple")
    result = contract.validate_checkout("http://user:pass@shop.example.com/pay", "apple")
    assert "cached" in result["reasons"][0]
