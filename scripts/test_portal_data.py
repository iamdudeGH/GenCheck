"""Exercise the portal's real-data helpers against a live transaction.

Confirms the consensus table and the cost line are built from genuine node
fields — and prints exactly what the page will render.

The three transactions below were chosen to cover the cases that broke the
portal during local testing:

  * a plain final transaction with full consensus data
  * one whose `leader_receipt` holds an errored duplicate of the leader address
  * one where the roster, not the vote map, has to carry the jury

Run:  .venv-deploy/Scripts/python scripts/test_portal_data.py
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gencheck import GenCheck
from portal.app import _consensus_detail, _fee_detail

CASES = [
    ("walmart cart (full consensus)",
     "0x1f877f92bd84e0779090beddfb1c04dac380f24dcd74b6fd4b151801d2b2882d"),
    ("walmart cart (leader retried after an error)",
     "0xcb9cc822e7affd4f1a36949ba8150a56782ae3f3d01ec2fd697951696d9efdec"),
    ("bestbuy cart (leader also voted)",
     "0xcbc2bf3cdacb880193eb3ce5181af0d4cb56331b68811466d39ea4fdcca82ef8"),
]

gc = GenCheck()
failures = []

for label, tx_hash in CASES:
    print(f"\n{'=' * 92}\n{label}   {tx_hash[:22]}…\n{'=' * 92}")
    tx = gc.client.get_transaction(tx_hash)
    cons = _consensus_detail(tx)
    fee = _fee_detail(tx)

    print(f"quorum    : {cons['quorum']}   complete={cons['complete']}")
    print(f"leader    : {cons['leader']['address'][:14]}  "
          f"model={cons['leader']['model'] or '—'}  "
          f"{cons['leader']['processing_time']}ms")
    print(f"cost      : {fee['cost_gen']} GEN  (held {fee['held_gen']}, "
          f"refunded {fee['refunded_gen']})  settled={fee['settled']}")

    print(f"\n{'role':<10} {'address':<16} {'model':<34} {'provider':<12} {'proc':>8} {'vote':>6}")
    print("-" * 92)
    for v in cons["validators"]:
        ms = v["processing_time"]
        try:
            n = float(ms)
            p = f"{n/1000:.1f} s" if n >= 1000 else f"{int(n)} ms"
        except (TypeError, ValueError):
            p = "—"
        print(f"{v['role']:<10} {v['address'][:14]:<16} {(v['model'] or '—'):<34} "
              f"{(v['provider'] or '—'):<12} {p:>8} {v['vote'] or '—':>6}")

    def check(cond, msg):
        if not cond:
            failures.append(f"{label}: {msg}")

    # invariants the page depends on
    check(cons["quorum"]["total"] == len(cons["validators"]), "quorum total mismatch")
    check(cons["quorum"]["total"] >= 5, "jury smaller than a round")
    check(cons["complete"], "consensus never reported complete")
    check(cons["validators"][0]["role"] == "leader", "leader not first")
    check(bool(cons["leader"]["model"]), "leader row has no model")
    check(bool(cons["leader"]["processing_time"]), "leader row has no timing")
    check(all(v["address"] for v in cons["validators"]), "blank address in table")
    check(fee["settled"], "fees not settled")
    check(bool(fee["cost_gen"]) and fee["cost_gen"] < fee["held_gen"],
          "cost should be < held")

print("\n" + ("FAILURES:\n  " + "\n  ".join(failures) if failures
              else "OK — all invariants hold across every case"))
sys.exit(1 if failures else 0)
