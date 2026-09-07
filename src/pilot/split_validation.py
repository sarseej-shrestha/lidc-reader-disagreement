"""Validation of the patient-level split manifest.

The split manifest itself is **private and never published**: it enumerates LIDC-IDRI
subject identifiers, including the locked-test membership. This module contains only the
*logic* that validates such a manifest, so the logic can be unit-tested in public against
synthetic data while the real manifest stays outside the repository.

Two consumers:

  * the default unit tests, which exercise every branch below on synthetic splits;
  * ``scripts/verify_private_split.py``, an explicit **integration** gate that runs the same
    logic against the real, ignored manifest and fails closed when it is not supplied.

**No function here returns, logs, or embeds a patient identifier.** Reports carry counts,
hashes and problem descriptions only. That is deliberate: a validator whose failure message
prints the thing it is protecting is not a control.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter

SPLIT_VALIDATION_VERSION = "split-validation-v1"

#: Frozen expectations for the real manifest (docs/protocol.md 5.2). These are already
#: public in the protocol; the *membership* they describe is not.
FROZEN_DEVELOPMENT_PATIENTS = 833
FROZEN_TEST_PATIENTS = 177
FROZEN_TEST_MEMBERSHIP_SHA256 = (
    "35fdf2b93ee883cf3633e2656d224df6376db9687f434760dc1df8d05e0c0983"
)


class SplitValidationError(RuntimeError):
    """Raised when a split manifest fails validation. Message carries no identifiers."""


def membership_hash(patient_ids) -> str:
    """Canonical membership hash, exactly as defined in docs/protocol.md 5.2:

        "SHA-256 of the sorted, newline-joined patient-ID list"

    This is a hash of the *membership*, not of the file, so it is invariant to formatting,
    key order and whitespace. Do not substitute a raw-file digest: the two answer different
    questions, and only this one certifies that the locked-test membership is unchanged.
    """
    return hashlib.sha256("\n".join(sorted(patient_ids)).encode()).hexdigest()


def load_split(path: str) -> dict:
    """Read a split manifest. Raises FileNotFoundError if absent -- callers must fail
    closed rather than treat absence as success."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def development_patients(data: dict) -> set:
    """Union of every fold's train and val partitions."""
    dev: set = set()
    for fold in data.get("folds") or []:
        dev |= set(fold.get("train") or [])
        dev |= set(fold.get("val") or [])
    return dev


def validate_split(
    data: dict,
    *,
    expected_development: int | None = None,
    expected_test: int | None = None,
    expected_test_membership_hash: str | None = None,
) -> dict:
    """Validate a split manifest. Returns a report; never raises on a data problem.

    Checks, in order:
      1. required partitions are present and well-formed;
      2. no patient appears in both development and locked test (patient-level disjointness);
      3. no duplicate membership within a partition;
      4. counts match, when an expectation is supplied;
      5. canonical membership hash matches, when an expectation is supplied.

    Counts and hashes are always reported. Identifiers never are.
    """
    problems: list[str] = []

    if not isinstance(data, dict):
        return {"ok": False, "problems": ["manifest is not a JSON object"],
                "validation_version": SPLIT_VALIDATION_VERSION}

    raw_test = data.get("test")
    folds = data.get("folds")
    if raw_test is None:
        problems.append("required partition 'test' is missing")
    elif not isinstance(raw_test, list):
        problems.append("partition 'test' is not a list")
    if folds is None:
        problems.append("required partition 'folds' is missing")
    elif not isinstance(folds, list) or not folds:
        problems.append("partition 'folds' is not a non-empty list")

    if problems:
        return {"ok": False, "problems": problems,
                "validation_version": SPLIT_VALIDATION_VERSION}

    test_list = list(raw_test)
    test_set = set(test_list)
    dev_set = development_patients(data)

    # -- duplicate membership -------------------------------------------------------
    dup_test = sum(c - 1 for c in Counter(test_list).values() if c > 1)
    if dup_test:
        problems.append(f"locked-test partition contains {dup_test} duplicate entrie(s)")
    for i, fold in enumerate(folds):
        for part in ("train", "val"):
            values = list(fold.get(part) or [])
            dups = sum(c - 1 for c in Counter(values).values() if c > 1)
            if dups:
                problems.append(f"fold {i} '{part}' contains {dups} duplicate entrie(s)")
        overlap = set(fold.get("train") or []) & set(fold.get("val") or [])
        if overlap:
            problems.append(f"fold {i} train and val share {len(overlap)} patient(s)")

    # -- patient-level disjointness -------------------------------------------------
    crossover = dev_set & test_set
    if crossover:
        problems.append(
            f"development and locked-test partitions share {len(crossover)} patient(s); "
            "they must be disjoint at the patient level"
        )

    # -- expected counts ------------------------------------------------------------
    if expected_development is not None and len(dev_set) != expected_development:
        problems.append(
            f"development count {len(dev_set)} != expected {expected_development}")
    if expected_test is not None and len(test_set) != expected_test:
        problems.append(f"locked-test count {len(test_set)} != expected {expected_test}")

    # -- canonical membership hash --------------------------------------------------
    observed_hash = membership_hash(test_set)
    if expected_test_membership_hash is not None and observed_hash != expected_test_membership_hash:
        problems.append(
            "locked-test membership hash mismatch: the frozen membership has changed "
            f"(observed {observed_hash[:8]}..., expected {expected_test_membership_hash[:8]}...)"
        )

    return {
        "ok": not problems,
        "problems": problems,
        "n_development": len(dev_set),
        "n_test": len(test_set),
        "n_total": len(dev_set | test_set),
        "n_folds": len(folds),
        "development_test_overlap": len(crossover),
        "test_membership_sha256": observed_hash,
        "validation_version": SPLIT_VALIDATION_VERSION,
    }


def assert_split_valid(data: dict, **expectations) -> dict:
    """`validate_split` that raises. Message carries counts only, never identifiers."""
    report = validate_split(data, **expectations)
    if not report["ok"]:
        raise SplitValidationError("; ".join(report["problems"]))
    return report


def resolve_manifest_path(explicit: str | None = None,
                          env_var: str = "LIDC_SPLIT_MANIFEST") -> str | None:
    """Where the private manifest is, from an explicit argument or the documented
    environment variable. Returns None when neither is supplied -- callers must treat that
    as a refusal, never as a pass."""
    if explicit:
        return os.path.expanduser(explicit)
    value = os.environ.get(env_var)
    return os.path.expanduser(value) if value else None
