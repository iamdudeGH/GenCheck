"""Integration tests for GenCheck ShoppingValidator contract.

These tests verify consensus behavior across validators with real (or
studio-net) web calls and LLM execution. Run with:
    gltest tests/integration/ -v -s

For local development:
    gltest tests/integration/ -v -s --network localnet

For Agent Tank hackathon:
    gltest tests/integration/ -v -s --network studio-dev
"""

import json
import pytest

from contracts.shopping_validator import ShoppingValidator


@pytest.mark.integration
class TestShoppingValidatorConsensus:
    """Integration tests that exercise full GenLayer consensus."""

    @pytest.fixture
    def deployed_contract(self, gltest):
        """Deploy a fresh ShoppingValidator contract for testing."""
        contract = ShoppingValidator()
        return gltest.deploy(ShoppingValidator)

    def test_validate_legitimate_checkout(self, deployed_contract, gltest):
        """
        Validate a real Apple checkout URL.
        This test calls gl.nondet.web.render and gl.nondet.exec_prompt,
        which will run across validators and reach consensus.
        """
        # Use a URL that is accessible from validators
        result = deployed_contract.validate_checkout(
            "https://www.apple.com/shop/checkout",
            "apple",
            # gltest config: specify gas, etc.
            **gltest.config
        )

        assert result["is_real"] is True
        assert result["verdict"] == "real"
        assert result["confidence"] > 0.7
        assert len(result["reasons"]) > 0

    def test_validate_scam_lookalike(self, deployed_contract, gltest):
        """
        Validate a known lookalike/scam URL.
        """
        result = deployed_contract.validate_checkout(
            "https://www.apple-pay-store.com/checkout",
            "apple",
            **gltest.config
        )

        assert result["is_real"] is False
        assert result["verdict"] in ("scam", "unsure")

    def test_cached_validation(self, deployed_contract, gltest):
        """
        Test that caching works across calls.
        First call should validate and cache, second call should return cached.
        """
        # First call
        result1 = deployed_contract.validate_checkout(
            "https://www.apple.com/shop/checkout",
            "apple",
            **gltest.config
        )
        assert result1["is_real"] is True

        # Second call - should use cache
        result2 = deployed_contract.validate_checkout(
            "https://www.apple.com/shop/checkout",
            "apple",
            **gltest.config
        )

        # Cached result should have confidence 1.0 and "cached" reason
        assert result2["confidence"] == 1.0
        assert "cached" in result2["reasons"][0]

    def test_domain_normalization(self, deployed_contract, gltest):
        """
        Test that domain extraction works correctly across URL formats.
        """
        test_cases = [
            "https://www.apple.com/checkout",
            "http://apple.com:443/checkout",
            "https://user:pass@apple.com/checkout",
        ]

        for url in test_cases:
            # Just verify the contract accepts these without crashing
            # (actual validation result depends on network/LLM)
            result = deployed_contract.validate_checkout(url, "apple", **gltest.config)
            assert "is_real" in result
            assert "verdict" in result

    def test_consensus_agreement(self, deployed_contract, gltest):
        """
        Verify the consensus mechanism: multiple validators agree on the verdict.
        The prompt_comparative principle should ensure is_real matches.
        """
        result = deployed_contract.validate_checkout(
            "https://www.apple.com/shop/checkout",
            "apple",
            **gltest.config
        )

        # If we got a result, consensus was reached
        # If validators disagreed, the transaction would fail or go to appeal
        assert result is not None
        assert result["verdict"] in ("real", "scam", "unsure")

    def test_add_official_domain(self, deployed_contract, gltest):
        """
        Test adding a new official domain to the registry.
        """
        deployed_contract.add_official_domain("testbrand", "testbrand.com", **gltest.config)

        # Verify the domain was added
        result = deployed_contract.validate_checkout(
            "https://testbrand.com/checkout",
            "testbrand",
            **gltest.config
        )
        assert "is_real" in result

    def test_is_site_validated(self, deployed_contract, gltest):
        """
        Test is_site_validated view method.
        """
        # Should return False for unvalidated
        assert deployed_contract.is_site_validated("never-validated.com") is False

        # Validate a site first
        deployed_contract.validate_checkout(
            "https://www.apple.com/shop/checkout",
            "apple",
            **gltest.config
        )

        # Should return True for validated real site
        assert deployed_contract.is_site_validated("apple.com") is True