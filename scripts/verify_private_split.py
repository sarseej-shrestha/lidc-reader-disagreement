#!/usr/bin/env python3
"""Integration gate: verify the REAL, private patient-level split manifest.

The manifest is deliberately **not** in this repository -- it enumerates LIDC-IDRI subject
identifiers including the locked-test membership. This command verifies the copy held
locally by the operator.

    python scripts/verify_private_split.py --manifest <path-to-private-manifest>
    LIDC_SPLIT_MANIFEST=<path> python scripts/verify_private_split.py

**This is an integration gate, not part of the default unit-test success claim.** The unit
suite exercises the same validation logic against synthetic data (see
`tests/pilot/test_pilot.py`); it cannot and does not certify the real split.

**Fails closed.** With no path supplied, or a path that does not exist, this exits **2** and
reports that the real split was NOT verified. It never reports success for input it did not
read.

Output is aggregate only -- counts and hashes. **No patient identifier is ever printed.**
This command reads the manifest and nothing else: it opens no CT series, loads no model, and
generates no prediction.

Exit codes:
    0  the real manifest was read and every check passed
    2  refused: no manifest supplied, or the supplied path does not exist
    1  the manifest was read but failed one or more checks
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pilot.split_validation import (  # noqa: E402
    FROZEN_DEVELOPMENT_PATIENTS,
    FROZEN_TEST_MEMBERSHIP_SHA256,
    FROZEN_TEST_PATIENTS,
    load_split,
    resolve_manifest_path,
    validate_split,
)

REFUSED = 2
FAILED = 1
OK = 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Verify the private patient-level split manifest (aggregate output only).")
    ap.add_argument("--manifest", default=None,
                    help="path to the private split manifest; "
                         "or set LIDC_SPLIT_MANIFEST")
    ap.add_argument("--expect-development", type=int, default=FROZEN_DEVELOPMENT_PATIENTS)
    ap.add_argument("--expect-test", type=int, default=FROZEN_TEST_PATIENTS)
    ap.add_argument("--expect-hash", default=FROZEN_TEST_MEMBERSHIP_SHA256)
    args = ap.parse_args(argv)

    path = resolve_manifest_path(args.manifest)
    if not path:
        print("REFUSED: no manifest supplied. Pass --manifest or set LIDC_SPLIT_MANIFEST.",
              file=sys.stderr)
        print("The real frozen split was NOT verified.", file=sys.stderr)
        return REFUSED
    if not os.path.isfile(path):
        # Deliberately does not echo the path: it is a private filesystem location.
        print("REFUSED: the supplied manifest path does not exist.", file=sys.stderr)
        print("The real frozen split was NOT verified.", file=sys.stderr)
        return REFUSED

    try:
        data = load_split(path)
    except Exception as exc:                                  # noqa: BLE001
        print(f"REFUSED: manifest could not be read ({type(exc).__name__}).", file=sys.stderr)
        print("The real frozen split was NOT verified.", file=sys.stderr)
        return REFUSED

    report = validate_split(
        data,
        expected_development=args.expect_development,
        expected_test=args.expect_test,
        expected_test_membership_hash=args.expect_hash,
    )

    print("private split manifest — aggregate verification")
    print(f"  development patients      : {report['n_development']} "
          f"(expected {args.expect_development})")
    print(f"  locked-test patients      : {report['n_test']} (expected {args.expect_test})")
    print(f"  development x test overlap: {report['development_test_overlap']} (expected 0)")
    print(f"  folds                     : {report['n_folds']}")
    print(f"  test membership sha256    : {report['test_membership_sha256']}")
    print(f"  matches frozen membership : "
          f"{report['test_membership_sha256'] == args.expect_hash}")
    print("  (no patient identifier is printed by this command)")

    if not report["ok"]:
        print("\nFAILED:", file=sys.stderr)
        for p in report["problems"]:
            print(f"  - {p}", file=sys.stderr)
        return FAILED

    print("\nPASS: the real frozen split was read and every check passed.")
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
