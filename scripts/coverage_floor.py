"""F47 — fail when backend LINE or BRANCH coverage drops under its floor.

`--cov-fail-under` in backend/pytest.ini gates coverage.py's single total, which with
`branch = True` blends lines and branches into one number. A blend can hide a branch slide
behind a line gain, so this checks the two separately from coverage.xml:

    python scripts/coverage_floor.py backend/coverage.xml --lines 90 --branches 78

The floors only go up. Set them a point under a measured run, never above it.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xml")
    ap.add_argument("--lines", type=float, required=True)
    ap.add_argument("--branches", type=float, required=True)
    args = ap.parse_args()

    root = ET.parse(args.xml).getroot()
    lines = 100 * int(root.get("lines-covered")) / max(1, int(root.get("lines-valid")))
    branches = 100 * int(root.get("branches-covered")) / max(1, int(root.get("branches-valid")))

    ok = True
    for name, got, floor in (("lines", lines, args.lines), ("branches", branches, args.branches)):
        verdict = "ok" if got >= floor else "BELOW FLOOR"
        print(f"{name:9s} {got:6.2f}%  floor {floor:6.2f}%  {verdict}")
        ok &= got >= floor
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
