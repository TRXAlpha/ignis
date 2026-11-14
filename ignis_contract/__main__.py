"""python -m ignis_contract validate data/bundle.json [--production] [--kind Bundle]
python -m ignis_contract flatten data/bundle.json > rows.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from . import FLAT_COLUMNS, check_bundle, flatten_bundle, is_valid, schema_errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ignis_contract")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("path")
    v.add_argument("--production", action="store_true", help="reject synthetic test sources")
    v.add_argument("--kind", default="Bundle", help="schema $defs name; non-Bundle kinds get schema checks only")
    fl = sub.add_parser("flatten")
    fl.add_argument("path")
    fl.add_argument("--all", action="store_true", help="include flagged/rejected rows")
    a = ap.parse_args(argv)

    with open(a.path, encoding="utf-8") as fh:
        obj = json.load(fh)

    if a.cmd == "validate":
        if a.kind == "Bundle":
            issues = check_bundle(obj, production=a.production)
            n = len(obj.get("observations", [])) if isinstance(obj, dict) else 0
        else:
            items = obj if isinstance(obj, list) else [obj]
            issues = [i for it in items for i in schema_errors(it, a.kind)]
            n = len(items)
        for i in issues:
            print(i)
        ok = is_valid(issues)
        print(f"{'OK' if ok else 'INVALID'}: {n} records, "
              f"{sum(i.level == 'error' for i in issues)} errors, {sum(i.level == 'warning' for i in issues)} warnings")
        return 0 if ok else 1

    issues = check_bundle(obj)
    if not is_valid(issues):
        print("refusing to flatten an invalid bundle; run validate", file=sys.stderr)
        return 1
    w = csv.DictWriter(sys.stdout, fieldnames=FLAT_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(flatten_bundle(obj, statuses=None if a.all else ("accepted", "human_verified")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
