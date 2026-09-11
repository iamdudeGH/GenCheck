"""Sample real fee data from the benchmark's fresh-consensus transactions."""
import re, sys, os
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gencheck import GenCheck

GC = GenCheck()
WEI = 10 ** 18

hashes = sorted(set(re.findall(r"0x[a-f0-9]{64}", open("BENCHMARK.md", encoding="utf-8").read())))


def cost(h):
    try:
        tx = GC.client.get_transaction(h)
    except Exception:
        return None
    f = tx.get("fees") or {}
    dep = int(f.get("deposit") or 0)
    c = f.get("consumed") or {}
    if not c:
        return None
    spent = (int(c.get("executionConsumed") or 0)
             + int(c.get("storageFeeUsed") or 0)
             + int(c.get("messageFeesConsumed") or 0))
    return dep, spent, c.get("leaderTimeunitsUsed"), c.get("validatorTimeunitsUsed")


with ThreadPoolExecutor(max_workers=8) as ex:
    rows = [r for r in ex.map(cost, hashes) if r]

print(f"sampled {len(rows)} transactions from BENCHMARK.md\n")
print(f"{'deposit (GEN)':>15} {'consumed (GEN)':>15} {'leader_tu':>10} {'val_tu':>8}")
print("-" * 52)
for dep, spent, ltu, vtu in rows[:25]:
    print(f"{dep/WEI:>15.9f} {spent/WEI:>15.9f} {str(ltu):>10} {str(vtu):>8}")

if rows:
    spent = [r[1] for r in rows]
    deps = [r[0] for r in rows]
    print("-" * 52)
    print(f"consumed: min {min(spent)/WEI:.9f}  max {max(spent)/WEI:.9f}  "
          f"mean {sum(spent)/len(spent)/WEI:.9f} GEN")
    print(f"deposit : min {min(deps)/WEI:.9f}  max {max(deps)/WEI:.9f}  (held, mostly refunded)")
    print(f"\n→ full consensus costs ~{sum(spent)/len(spent)/WEI:.6f} GEN "
          f"= ~{1/(sum(spent)/len(spent)/WEI):,.0f} per GEN")
