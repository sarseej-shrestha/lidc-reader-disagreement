#!/usr/bin/env python3
"""Build the frozen 600-pair reference manifest and the 120-item repeat subset.

Read-only with respect to LIDC data. Writes only to an output directory OUTSIDE the git
worktree. Creates no labels: this script produces review *items*, never decisions.

Locked-test protection: the locked-test patient list is loaded solely to assert the frozen
hash and to build an exclusion set. No locked-test series is opened, and no locked-test
annotation or image is read.

Both paths are required arguments; nothing about the operator's filesystem layout is baked
into this file.

    python scripts/build_pilot_manifest.py \
        --corpus <extracted-LIDC-XML-dir> \
        --out <output-dir-outside-the-repository>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pilot import manifest as M
from src.pilot import matching as MT
from src.pilot import pool as POOL
from src.pilot import xml_extract as X

LOCKED_TEST_HASH = "35fdf2b93ee883cf3633e2656d224df6376db9687f434760dc1df8d05e0c0983"
SEED_SAMPLE = 20260831
SEED_ORDER = 20260901


def resolve_output_dir(out: str, repo: str) -> str:
    """Resolve `--out` and refuse any location inside the git worktree.

    `realpath` rather than `abspath`: a symlink pointing into the repository would slip
    past a purely lexical check. The equality case is separate from the prefix case
    because `repo` itself does not start with `repo + os.sep` -- pointing `--out` at the
    repository root would otherwise have been permitted, which is exactly the outcome this
    guard exists to prevent.
    """
    out_root = os.path.realpath(os.path.expanduser(out))
    repo_root = os.path.realpath(repo)
    if out_root == repo_root or out_root.startswith(repo_root + os.sep):
        raise SystemExit(
            f"refusing to write inside the git worktree: {out_root}\n"
            "The private mapping carries patient IDs, series UIDs, session indices and "
            "physical distances. It must never be written where it could be committed."
        )
    return out_root


def load_splits(path: str) -> tuple[set[str], set[str], str]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    test = sorted(data["test"])
    digest = hashlib.sha256("\n".join(test).encode()).hexdigest()
    if digest != LOCKED_TEST_HASH:
        raise SystemExit(f"locked-test membership hash mismatch: {digest}")
    dev: set[str] = set()
    for fold in data["folds"]:
        dev |= set(fold["train"]) | set(fold["val"])
    if dev & set(test):
        raise SystemExit("development/locked-test overlap detected")
    with open(path, "rb") as fh:
        split_id = hashlib.sha256(fh.read()).hexdigest()
    return dev, set(test), split_id


def main() -> int:
    ap = argparse.ArgumentParser()
    # No default: a hardcoded absolute path would bake one machine's layout into public
    # code and make the corpus location invisible in the run record. Both must be stated.
    ap.add_argument("--corpus", required=True,
                    help="directory holding the extracted, hash-pinned LIDC annotation XML "
                         "(protocol 3.1)")
    ap.add_argument("--splits", default="input/splits/patient_splits.json",
                    help="repository-relative frozen patient split file")
    ap.add_argument("--out", required=True,
                    help="output directory; must be OUTSIDE the git worktree")
    args = ap.parse_args()

    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_root = resolve_output_dir(args.out, repo)

    dev, test, split_id = load_splits(args.splits)
    print(f"development patients: {len(dev)}   locked-test: {len(test)} (never opened)")

    import src.pylidc_compat  # noqa: F401
    import pylidc as pl
    scans = {s.series_instance_uid: s for s in pl.query(pl.Scan).all()}

    by_series, roots = X.index_corpus(args.corpus)
    n_xml = sum(roots.values())
    print(f"corpus: {n_xml} xml files, root tags: "
          f"{ {str(k).split('}')[-1]: v for k, v in roots.items()} }")
    print(f"distinct CT series: {len(by_series)}")

    records, selection_log, marks_by_series = [], [], {}
    for series_uid in sorted(by_series):
        scan = scans.get(series_uid)
        if scan is None:
            selection_log.append({"series_uid": series_uid, "rule": "no_scan_record__skip"})
            continue
        path, rule = X.select_source_file(series_uid, by_series[series_uid])
        selection_log.append({
            "series_uid": series_uid, "rule": rule,
            "selected": os.path.basename(path) if path else None,
            "n_candidates": len(by_series[series_uid]),
        })
        if path is None:
            continue
        thickness = float(scan.slice_thickness or 0.0)
        spacing = abs(float(getattr(scan, "slice_spacing", 0.0) or 0.0)) or thickness or 1.0
        rec = X.extract_scan(path, scan.patient_id, float(scan.pixel_spacing), spacing)
        records.append(rec)
        if rec.excluded_reason or scan.patient_id not in dev:
            continue
        marks_by_series[series_uid] = (
            rec.patient_id, rec.study_uid, rec.marks, thickness)

    summary = X.summarise(records, scope="corpus")
    primary = X.summarise(records, scope="primary")
    print("\n=== extraction reconciliation ===")
    print("  CORPUS scope (all CT series, incl. the excluded reader panel) -- the gate:")
    for k, v in sorted(summary["counts"].items()):
        print(f"    {k:24s} {v:>8,}")
    print(f"    sessions_per_series    {summary['sessions_per_series']}")
    X.assert_reconciled(summary, xml_files=n_xml, ct_series=len(by_series))
    print("  GATE: corpus-scope reconciliation PASS")
    print("  PRIMARY-ANALYSIS scope (reader panel excluded):")
    for k, v in sorted(primary["counts"].items()):
        print(f"    {k:24s} {v:>8,}")
    X.assert_reconciled(primary, xml_files=n_xml, ct_series=len(by_series),
                        expected={**X.EXPECTED_PRIMARY, "xml_files": n_xml,
                                  "ct_series": len(by_series)})
    print("  GATE: primary-scope cross-check PASS "
          f"(difference = the excluded panel's {X.EXCLUDED_PANEL_MARK_COUNTS['total']} marks)")

    pairs = POOL.build_pool(marks_by_series)
    pool_summary = POOL.summarise_pool(pairs)
    print("\n=== eligible pool ===")
    print(json.dumps(pool_summary, indent=2, sort_keys=True))
    POOL.assert_pool_reconciled(pool_summary)
    print("  GATE: pool reconciliation PASS")

    # ---- joint feasibility proof, printed BEFORE anything is written -------------
    from collections import defaultdict
    availability = defaultdict(set)
    for p in pairs:
        availability[p.patient_id].add(POOL.cell_of(p))
    pins, deferred = M.select_mandatory_pins(pairs)
    probe = MT.assign_patients(dict(availability), SEED_SAMPLE, MT.CELL_QUOTAS,
                               {pid: POOL.cell_of(pair) for pid, pair in pins.items()})
    print("\n=== joint capacity-constrained feasibility proof ===")
    print(json.dumps(probe.proof(), indent=2, sort_keys=True))
    if not probe.feasible:
        raise SystemExit(
            "JOINT QUOTAS INFEASIBLE -- stopping without writing a manifest.\n"
            + json.dumps({"failure_reason": probe.failure_reason,
                          "diagnosis": probe.diagnosis}, indent=2, sort_keys=True))
    print("  GATE: joint max-flow feasibility PASS "
          f"({probe.achieved_flow + len(probe.pinned)}/{MT.TOTAL_QUOTA})")

    built = M.build_primary_manifest(pairs, SEED_SAMPLE, SEED_ORDER)
    print("\n=== manifest composition ===")
    print(json.dumps(built.composition, indent=2, sort_keys=True))
    blinding = M.audit_blinding(built.reviewer_rows)
    if not blinding["pass"]:
        raise SystemExit(f"blinding audit FAILED: {blinding}")
    print("  GATE: blinding audit PASS")

    # ---- input-order invariance: 20 shuffled-input rebuilds must agree byte-for-byte ----
    import random as _random

    def _round_hash(rows):
        return M.canonical_hash(rows, M.REVIEWER_COLUMNS)

    ref_repeat, ref_repeat_priv = M.build_repeat_subset(built.private_rows, SEED_SAMPLE)
    ref_census, _ = M.build_census_manifest(
        built.deferred_radius_expanded, built.private_rows, SEED_SAMPLE, SEED_ORDER)
    ref = {
        "reviewer": built.reviewer_hash,
        "private": built.private_hash,
        "repeat": _round_hash(ref_repeat),
        "independent": _round_hash(M.build_independent_manifest(ref_repeat_priv, SEED_ORDER)),
        "census": _round_hash(ref_census),
    }
    perm = {"repetitions": 0, "reference_hashes": ref, "mismatches": [],
            "shuffle_seeds": [], "artifacts_compared": sorted(ref)}
    for rep in range(20):
        rng = _random.Random(90000 + rep)
        shuffled_input = {}
        for uid in rng.sample(sorted(marks_by_series), len(marks_by_series)):
            pid, sid, marks, thick = marks_by_series[uid]
            ms = list(marks)
            rng.shuffle(ms)
            shuffled_input[uid] = (pid, sid, ms, thick)
        alt_pool = POOL.build_pool(shuffled_input)
        rng.shuffle(alt_pool)                       # also shuffle the pool order itself
        alt = M.build_primary_manifest(alt_pool, SEED_SAMPLE, SEED_ORDER)
        alt_repeat, alt_repeat_priv = M.build_repeat_subset(alt.private_rows, SEED_SAMPLE)
        alt_census, _ = M.build_census_manifest(
            alt.deferred_radius_expanded, alt.private_rows, SEED_SAMPLE, SEED_ORDER)
        got = {
            "reviewer": alt.reviewer_hash,
            "private": alt.private_hash,
            "repeat": _round_hash(alt_repeat),
            "independent": _round_hash(
                M.build_independent_manifest(alt_repeat_priv, SEED_ORDER)),
            "census": _round_hash(alt_census),
        }
        perm["repetitions"] += 1
        perm["shuffle_seeds"].append(90000 + rep)
        if got != ref or len(alt_pool) != len(pairs):
            perm["mismatches"].append({
                "shuffle_seed": 90000 + rep, "hashes": got, "pool_size": len(alt_pool),
                "differing": sorted(k for k in ref if ref[k] != got.get(k)),
            })
    perm["byte_identical"] = not perm["mismatches"]
    print(f"\n=== permutation check: {perm['repetitions']} shuffled-input rebuilds, "
          f"byte-identical={perm['byte_identical']} ===")
    if not perm["byte_identical"]:
        raise SystemExit(f"input-order invariance FAILED: {perm['mismatches'][:2]}")

    repeat_reviewer, repeat_private = M.build_repeat_subset(built.private_rows, SEED_SAMPLE)
    independent_reviewer = M.build_independent_manifest(repeat_private, SEED_ORDER)
    census_reviewer, census_private = M.build_census_manifest(
        built.deferred_radius_expanded, built.private_rows, SEED_SAMPLE, SEED_ORDER)

    audits = {"primary": blinding}
    for name, rows in (("repeat", repeat_reviewer), ("independent", independent_reviewer),
                       ("radius_expanded_census", census_reviewer)):
        audits[name] = M.audit_blinding(rows)
        if not audits[name]["pass"]:
            raise SystemExit(f"{name} blinding audit FAILED: {audits[name]}")
    print("  GATE: blinding audit PASS on all four reviewer manifests")

    coverage = M.audit_radius_expanded_coverage(pairs, built.private_rows, census_private)
    print("\n=== radius-expanded-only coverage ===")
    print(json.dumps(coverage, indent=2, sort_keys=True))
    if not coverage["pass"]:
        raise SystemExit(f"radius-expanded coverage audit FAILED: {coverage}")
    print("  GATE: every radius-expanded-only pair reaches human review exactly once")

    md = os.path.join(out_root, "manifests")
    outputs = {}
    outputs["primary_manifest.csv"] = M.write_csv(
        os.path.join(md, "primary_manifest.csv"), built.reviewer_rows, M.REVIEWER_COLUMNS)
    outputs["repeat_manifest.csv"] = M.write_csv(
        os.path.join(md, "repeat_manifest.csv"), repeat_reviewer, M.REVIEWER_COLUMNS)
    outputs["independent_manifest.csv"] = M.write_csv(
        os.path.join(md, "independent_manifest.csv"), independent_reviewer,
        M.REVIEWER_COLUMNS)
    outputs["radius_expanded_census_manifest.csv"] = M.write_csv(
        os.path.join(md, "radius_expanded_census_manifest.csv"), census_reviewer,
        M.REVIEWER_COLUMNS)
    private_cols = tuple(built.private_rows[0].keys())
    outputs["PRIVATE_mapping.csv"] = M.write_csv(
        os.path.join(md, "PRIVATE_mapping.csv"), built.private_rows, private_cols)
    outputs["PRIVATE_repeat_mapping.csv"] = M.write_csv(
        os.path.join(md, "PRIVATE_repeat_mapping.csv"), repeat_private,
        tuple(repeat_private[0].keys()))
    outputs["PRIVATE_census_mapping.csv"] = M.write_csv(
        os.path.join(md, "PRIVATE_census_mapping.csv"), census_private,
        tuple(census_private[0].keys()))
    outputs["matching_proof.json"] = M.write_json(
        os.path.join(md, "matching_proof.json"), built.matching_proof)
    outputs["selection_log.json"] = M.write_json(
        os.path.join(md, "selection_log.json"), {"entries": selection_log})
    outputs["permutation_check.json"] = M.write_json(
        os.path.join(md, "permutation_check.json"), perm)
    outputs["blinding_audit.json"] = M.write_json(
        os.path.join(md, "blinding_audit.json"), audits)
    outputs["radius_expanded_coverage.json"] = M.write_json(
        os.path.join(md, "radius_expanded_coverage.json"), coverage)
    outputs["canonical_hashes"] = json.dumps({
        "reviewer_manifest_canonical": built.reviewer_hash,
        "private_manifest_canonical": built.private_hash,
    })

    src_dir = os.path.join(repo, "src", "pilot")
    source_files = [os.path.join(src_dir, f) for f in sorted(os.listdir(src_dir))
                    if f.endswith(".py")]
    prov = M.build_provenance(
        split_id=split_id, seed=SEED_SAMPLE, seed_order=SEED_ORDER, outputs=outputs,
        source_files=source_files, pool_summary=pool_summary,
        extraction_summary={"corpus": summary["counts"], "primary": primary["counts"]},
    )
    prov["reviewer_manifest_canonical_hash"] = built.reviewer_hash
    prov["private_manifest_canonical_hash"] = built.private_hash
    prov["round_canonical_hashes"] = perm["reference_hashes"]
    prov["composition"] = built.composition
    prov["radius_expanded_coverage"] = coverage
    prov["matching_proof"] = built.matching_proof
    prov["reference_labels_created"] = 0
    prov["threshold_selected"] = None
    M.write_json(os.path.join(md, "manifest_provenance.json"), prov)

    print("\n=== written (outside the repo) ===")
    for name, digest in outputs.items():
        if name != "canonical_hashes":
            print(f"  {name:32s} sha256={digest[:16]}…")
    print(f"  reviewer canonical hash: {built.reviewer_hash}")
    print(f"  private  canonical hash: {built.private_hash}")
    print("\nZERO labels created. This script produces review items only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
