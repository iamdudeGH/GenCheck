# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }

import json
import typing

import genlayer as gl
from genlayer.types import *

# Read-only seed data (module constant — NOT contract storage; never mutated).
# The mutable, persisted registry is the official_domains TreeMap field.
SEED_BRANDS = {
    "apple": "apple.com",
    "amazon": "amazon.com",
    "paypal": "paypal.com",
    "microsoft": "microsoft.com",
    "google": "google.com",
    "netflix": "netflix.com",
    "spotify": "spotify.com",
    "github": "github.com",
}


class ShoppingValidator(gl.contract.Contract):
    """
    GenCheck: Shopping URL Validator

    Before money moves, GenCheck asks GenLayer validators to open a checkout URL
    and the real brand's official site, then answer: is this the real seller or
    a lookalike scam? Real → allow pay. Fake or unsure → block pay.
    """

    # Cache: domain -> is_real (validated result)
    validated_sites: gl.storage.TreeMap[str, bool]
    # Brand registry: brand name -> official domain (persisted, admin-managed)
    official_domains: gl.storage.TreeMap[str, str]

    def __init__(self):
        for brand, domain in SEED_BRANDS.items():
            self.official_domains[brand] = domain

    @gl.public.write
    def validate_checkout(self, checkout_url: str, brand: str) -> dict[str, typing.Any]:
        """
        Validates a checkout URL by comparing it against the official brand site.

        Args:
            checkout_url: The URL of the checkout page to validate
            brand: The brand name (e.g., "apple", "amazon")

        Returns:
            dict with keys: is_real, confidence, reasons, evidence, verdict
        """
        # Extract domain from URL
        domain = self._extract_domain(checkout_url)

        # Quick cache check - if we've validated this domain before, return cached result
        if domain in self.validated_sites:
            is_real = self.validated_sites[domain]
            return {
                "is_real": is_real,
                "confidence": 100,
                "reasons": ["cached from previous validation"],
                "evidence": [],
                "verdict": "real" if is_real else "blocked",
            }

        # Pre-compute deterministic values BEFORE the non-deterministic block
        # so every validator builds the identical prompt inputs
        official_domain = self.official_domains.get(brand.lower())

        def get_validation_result() -> str:
            # ALL non-deterministic calls live inside this closure so they are
            # reachable from the equivalence principle block below

            # Unfetchable checkout page: there is nothing to judge. Return a
            # deterministic "unverifiable" verdict instead of raising, so the
            # transaction completes, the block is explicit, and the verdict is
            # cacheable. (If the leader raised here, the tx would end
            # FINISHED_WITH_ERROR with no cache entry — the pre-v0.4 behavior.)
            try:
                checkout_page = gl.nondet.web.render(checkout_url, mode="text")
            except Exception:
                return json.dumps({
                    "is_real": False,
                    "confidence": 0.0,
                    "reasons": [
                        "checkout page could not be fetched by validators "
                        f"(bot-blocking or offline): {checkout_url}",
                    ],
                    "evidence": [],
                    "verdict": "unverifiable",
                })

            # If the official page is unfetchable, fall back to the LLM's
            # general knowledge of the brand instead of failing the whole
            # validation.
            official_page = None
            if official_domain:
                try:
                    official_page = gl.nondet.web.render(
                        f"https://{official_domain}", mode="text"
                    )
                except Exception:
                    official_page = None

            # Build the LLM prompt using the fetched pages
            prompt = self._build_validation_prompt(
                checkout_url, checkout_page, official_page, official_domain, brand
            )

            result = gl.nondet.exec_prompt(prompt)
            # Strip markdown code fences if present
            result = result.replace("```json", "").replace("```", "").strip()
            return result

        # Execute with consensus via prompt_comparative
        # This ensures validators agree on the verdict, not just the exact wording
        result = gl.eq_principle.prompt_comparative(
            get_validation_result,
            "The is_real verdict must match. If one validator says the site is real "
            "and another says it is a scam, they do not match."
        )

        result_json = json.loads(result)

        # The runner's calldata encoder cannot serialize floats, so confidence
        # is normalized to an integer percent (0-100). Defensive: the LLM may
        # return the field as string, missing, or non-numeric.
        try:
            result_json["confidence"] = int(round(float(result_json["confidence"]) * 100))
        except (KeyError, TypeError, ValueError):
            result_json["confidence"] = 0

        # Cache the result for future validations
        self.validated_sites[domain] = result_json["is_real"]

        return result_json

    @gl.public.view
    def is_site_validated(self, domain: str) -> bool:
        """Check if a domain has been validated and is considered real"""
        return domain in self.validated_sites and self.validated_sites[domain]

    @gl.public.view
    def get_cached_result(self, domain: str) -> dict[str, typing.Any]:
        """Get the cached validation result for a domain"""
        if domain not in self.validated_sites:
            raise gl.vm.UserError("Domain not yet validated")
        return {
            "domain": domain,
            "is_real": self.validated_sites[domain],
        }

    @gl.public.write
    def add_official_domain(self, brand: str, domain: str) -> None:
        """Admin-only: register a new official brand domain"""
        self.official_domains[brand.lower()] = domain

    @gl.public.view
    def get_official_domain(self, brand: str) -> str:
        """Look up the registered official domain for a brand"""
        return self.official_domains.get(brand.lower(), "")

    def _extract_domain(self, url: str) -> str:
        """Extract the domain from a URL without external imports"""
        if "://" in url:
            url = url.split("://", 1)[1]
        if "/" in url:
            url = url.split("/", 1)[0]
        if "@" in url:
            url = url.split("@", 1)[1]
        if ":" in url:
            url = url.split(":", 1)[0]
        return url.lower()

    def _build_validation_prompt(
        self,
        checkout_url: str,
        checkout_page: str,
        official_page: typing.Optional[str],
        official_domain: typing.Optional[str],
        brand: typing.Optional[str] = None,
    ) -> str:
        """Build the LLM prompt for URL validation"""
        claimed_brand = brand or "the claimed brand"
        if official_page:
            official_section = f"""
OFFICIAL PAGE OF THE CLAIMED BRAND "{claimed_brand}" (from {official_domain}):
{official_page[:2000]}
"""
        else:
            official_section = f"""
OFFICIAL PAGE OF THE CLAIMED BRAND "{claimed_brand}": NOT PROVIDED (brand not
in registry — use your general knowledge of {claimed_brand}'s real official
domain instead).
"""

        return f"""
You are a security expert validating whether a checkout URL is the REAL seller
for a claimed brand.

CLAIMED BRAND: {claimed_brand}
The brand the customer intends to buy from is "{claimed_brand}". You are NOT
validating whatever brand the page itself displays — you are validating whether
this page legitimately belongs to "{claimed_brand}".

CHECKOUT URL: {checkout_url}

CHECKOUT PAGE CONTENT:
{checkout_page[:2000]}

{official_section}

PRIMARY CRITERION — DOMAIN OWNERSHIP (this alone decides is_real):
The checkout URL is "{claimed_brand}"'s real seller ONLY if its domain IS
"{claimed_brand}"'s official domain, or a subdomain of it (e.g.
store.google.com for google.com, open.spotify.com for spotify.com). Answer
this question first, and let it decide the verdict:
  Does the checkout URL's domain belong to "{claimed_brand}"?

A page being a legitimate, safe, well-known site is NOT sufficient, and
neither is the page displaying its own (different) brand's logos. If the
domain belongs to a different company — even a reputable one (e.g.
music.apple.com for "spotify", walmart.com for "amazon") — it is NOT
"{claimed_brand}"'s real seller.

Decision rules, in order:
1. Checkout domain is "{claimed_brand}"'s official domain or a subdomain of
   it, and the page branding matches "{claimed_brand}" → is_real: true,
   verdict: "real"
2. Checkout domain belongs to a different legitimate site → is_real: false,
   verdict: "wrong_seller"
3. Checkout domain mimics the official domain (typosquatting, homoglyphs,
   subdomain tricks) or the page copies "{claimed_brand}"'s design to
   impersonate it (e.g. a "{claimed_brand}" lookalike hosted on github.io,
   blogspot, netlify, vercel, or an unrelated domain) → is_real: false,
   verdict: "scam"
4. Cannot determine → is_real: false, verdict: "unsure"

Secondary signals (use to choose between rules 2 and 3, never to override
the domain rule):
- Domain similarity to the official domain (typosquatting, homoglyphs, subdomain tricks)
- Page design, branding, checkout flow
- Payment methods, trust badges, contact information
- URL structure and redirects
- Any suspicious elements (misspellings, unusual TLDs, etc.)

Respond ONLY with JSON (no markdown, no extra text, no code fences):
{{
  "is_real": bool,
  "confidence": float,
  "reasons": ["reason1", "reason2"],
  "evidence": ["url1", "url2"],
  "verdict": "real|scam|wrong_seller|unsure"
}}
"""