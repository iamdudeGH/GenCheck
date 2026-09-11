---
name: gencheck
description: Pre-payment trust gate for shopping agents. Before an agent pays a checkout URL, GenCheck sends the URL plus the claimed brand to GenLayer validator consensus — independent validators fetch the checkout page and the brand's official site, then vote on whether this is the brand's real seller or a lookalike/wrong-brand scam. Use this BEFORE signing or executing any payment for a checkout URL, especially for unfamiliar domains, links arriving from email/chat/search results, or any URL whose domain does not obviously match the brand being purchased from.
---

# GenCheck — verify the seller before your agent pays

An agent that pays a checkout URL is trusting that the page is the merchant it claims
to be. Phishing kits and lookalike storefronts exploit exactly that gap. GenCheck closes
it: a smart contract on GenLayer asks a decentralized validator set one question, and
returns a verdict your agent can act on.

**The question validators answer:** is this checkout URL the claimed brand's real
seller, or a lookalike / wrong-brand scam?

## The one rule

```
pay ONLY when is_real is true
```

Everything else means **BLOCK** — `scam`, `wrong_seller`, `unsure`, `unverifiable`, an
error, or *no verdict at all*. The gate fails closed. A validator that cannot fetch a
page (bot-blocking, offline, Cloudflare wall) produces `unverifiable`, which is a
**block**, never a pass.

Do not soften this rule. A blocked legitimate purchase costs a retry; a paid phishing
page costs the wallet.

## Setup (MCP — zero integration code)

GenCheck ships an MCP server exposing the three tools below. Works with Claude Code,
Cursor, or any MCP-capable agent:

```bash
claude mcp add gencheck \
  --env GENCHECK_PRIVATE_KEY=0x… \
  -- python -m gencheck.mcp_server
```

The private key is **only needed for new-domain validations** (writes). Without it,
cached reads still work — pass it in the server's `env`, not the shell, because MCP
stdio clients start servers with a minimal default environment.

## Tools

### `gencheck_check_domain(domain)`

Free and instant — reads the on-chain verdict cache. Call this **first**: if the domain
was already judged, you get the consensus verdict with no cost and no wait.

```
{ "domain": "www.amazon.com", "status": "cached_consensus_verdict",
  "is_real": true, "decision": "PAY", "reason": "…" }
```

A domain that has never been validated returns `status: "never_validated"` and
`decision: "BLOCK"` — escalate to `gencheck_validate` if you want a real answer.

### `gencheck_validate(checkout_url, brand)`

Full validator consensus, submitted as **a real transaction**. Validators independently
fetch the checkout page **and** the claimed brand's official site, then vote. Fails
closed. The contract caches each domain's verdict on-chain, so a later call on a known
domain returns the stored verdict quickly — still a real transaction, just without a
fresh LLM round.

```
{ "checkout_url": "…", "brand": "amazon", "status": "consensus_verdict",
  "is_real": false, "verdict": "wrong_seller", "confidence": 99,
  "reasons": ["The checkout URL's domain is vardhan2k3.github.io, which is not amazon.com …"],
  "decision": "BLOCK", "decision_reason": "…" }
```

### `gencheck_official_domain(brand)`

The registered official domain for a brand, or null if unknown. Useful to pre-check a
suspicious URL yourself before spending a consensus round.

## Usage pattern

```
1. domain = extract domain from checkout_url
2. r = gencheck_check_domain(domain)          # free, instant
3. if r.status == "never_validated":
       r = gencheck_validate(checkout_url, brand)   # consensus, costs fees
4. if r.decision != "PAY":  halt — do not sign or send payment
5. else: proceed with payment
```

## Cost and latency

| | |
|---|---|
| `gencheck_validate` | **one real transaction**, ~0.00008 GEN |
| `gencheck_check_domain`, `gencheck_official_domain` | free read — no transaction, no hash |
| First check of a domain | full validator consensus (validators fetch and reason) |
| Repeat check of a known domain | contract returns its cached verdict; still a real transaction, just no LLM round |

**Two caches — do not confuse them:**

- `gencheck_check_domain` is a **free read** of an existing verdict. No transaction is
  created and there is no hash to show. Use it to answer cheaply.
- `gencheck_validate` **always writes a real transaction with a hash**, even when the
  contract answers from its own domain cache. Use it when you need on-chain proof, or
  when the domain has never been judged.

On-chain verdicts are cached permanently, so a merchant is only ever fully re-investigated
once per contract — but note that the contract is immutable, so a verdict that was wrong
cannot be re-judged on the same deployment.

## No MCP? Use the HTTP API

The portal exposes the same gate over plain HTTP. Validate asynchronously — submit, then
poll, so no request is held open during consensus:

```bash
# 1. submit — always returns a transaction hash to poll
curl -s -X POST https://<portal>/api/submit \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com/checkout","brand":"example"}'
# → {"status":"pending","tx_id":"0x…","domain":"example.com"}

# 2. poll until stage == "final"
curl -s "https://<portal>/api/status?tx_id=0x…&url=…&brand=…"
# → {"stage":"final","verdict":{…},"consensus":{"validators":[…],"leader":{…}}}
```

`/api/status` returns real chain state: every validator's address, vote, and the LLM
model that ran it, plus the leader's model and processing time. When served from the
portal, this skill file lives at the same origin — `GET /skill.md`.

`POST /api/check` is the blocking variant (holds the request through consensus); use it
only on long-lived servers.

## What validators actually do

Each validator independently fetches the checkout URL and the brand's official site,
then reasons over domain ownership, page content, branding, and impersonation
heuristics, and submits a signed vote. GenLayer's consensus tallies the votes; the
resulting verdict is written on-chain. The reasoning is not a black box — the verdict
carries the validators' `reasons`, and the full jury (addresses, votes, models) is
readable from the transaction.

## Live deployment

| | |
|---|---|
| Network | studio-dev (chain 61997) |
| Contract | `0x61153C8d907eBa4Ea96d5955c7b05F67F2967e2D` |
| Explorer | https://explorer-studio-dev.genlayer.com |
| Working demo agent | `demo/shopping_agent.py` |

Every verdict is a real transaction — verify any of them independently on the explorer.

## Scope

GenCheck gates a payment **before** it happens. It is not a dispute-resolution or
escrow layer: it holds no funds and takes no custody. Agents that need adjudication
*after* a transaction are solving a different problem — GenCheck is the check that runs
first, and it composes with whatever settlement layer you already use.
