"""Keep every copy of the agent skill byte-identical.

`SKILL.md` is served and shipped from four places, and each one is read by a
different consumer:

    SKILL.md                              the repo / GitHub browsers
    portal/static/skill.md                served live at GET /skill.md
    .claude/skills/gencheck/SKILL.md      this repo's own Claude Code sessions
    plugins/gencheck/skills/gencheck/SKILL.md   the installable plugin

They must never drift. This project has already lost a deploy to exactly that
failure mode — two files that had to agree, where only one was read by any
given consumer and a mismatch was silent (see the pyproject.toml note in
`.vercelignore`). Four hand-maintained copies is four chances to repeat it.

The root file is canonical: edit it, then run this.

    python scripts/check_skill_sync.py          # report drift, exit 1 if any
    python scripts/check_skill_sync.py --fix    # copy the canonical file out
"""

import argparse
import hashlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CANONICAL = "SKILL.md"
COPIES = [
    "portal/static/skill.md",
    ".claude/skills/gencheck/SKILL.md",
    "plugins/gencheck/skills/gencheck/SKILL.md",
]


def digest(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true",
                    help="overwrite every copy with the canonical SKILL.md")
    args = ap.parse_args()

    src = os.path.join(ROOT, CANONICAL)
    if not os.path.exists(src):
        print(f"canonical skill not found: {CANONICAL}")
        return 2

    want = digest(src)
    size = os.path.getsize(src)
    print(f"canonical  {want[:8]}  {size}B  {CANONICAL}\n")

    drifted = []
    for rel in COPIES:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print(f"  MISSING  {rel}")
            drifted.append(rel)
            continue
        have = digest(path)
        if have == want:
            print(f"  ok       {rel}")
        else:
            print(f"  DRIFT    {rel}  {have[:8]}")
            drifted.append(rel)

    if not drifted:
        print("\nall copies identical")
        return 0

    if not args.fix:
        print(f"\n{len(drifted)} cop{'y' if len(drifted) == 1 else 'ies'} out of sync."
              f"\nEdit {CANONICAL}, then re-run with --fix.")
        return 1

    for rel in drifted:
        dest = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        print(f"  wrote    {rel}")
    print("\nsynced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
