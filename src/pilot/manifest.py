"""Reference-set manifest construction, blinding, hashing, and provenance.

Two artifacts with deliberately different content:

  * the REVIEWER manifest carries an opaque review_item_id and nothing else that could
    inform or bias a judgement -- no patient/series/session identity, no category, no vote,
    no entropy, no distance, no threshold, no model output, and no filename encoding any of
    those;
  * the PRIVATE mapping carries the identifying and analytic fields, and never reaches the
    review interface.

The canonical manifest hash is computed over a field-ordered serialisation so that shuffled
input produces a byte-identical hash.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .matching import (CELL_QUOTAS, MATCHING_VERSION, PAIR_TYPE_QUOTAS, assign_patients,
                       patient_priority)
from .pool import (POOL_VERSION, Pair, cell_of, contour_size_band, distance_band,
                   enrichment_band, is_grid_discriminating, is_near_miss, thickness_band)
from .xml_extract import CORPUS_SHA256, EXTRACTION_VERSION, GEOMETRY_VERSION

MANIFEST_VERSION = "reference_pairs_v2"
REPEAT_MANIFEST_VERSION = "repeat_subset_v2"
CENSUS_MANIFEST_VERSION = "radius_expanded_census_v1"
N_PRIMARY = 600
N_REPEAT = 120

#: Round names. `repeat` is the intra-rater re-review after the washout; `independent` is
#: the same 120 items shown to a second reviewer as an external reproducibility audit;
#: `radius_expanded_census` is the supplemental mandatory-coverage round (protocol 4.6.4)
#: whose results are kept out of the primary Wilson precision calculation.
ROUNDS = ("primary", "repeat", "independent", "radius_expanded_census")

#: Fields that must NEVER appear in a reviewer-facing manifest (protocol 4.6).
FORBIDDEN_REVIEWER_FIELDS = frozenset({
    "patient_id", "study_uid", "series_uid",
    "mark_id_a", "mark_id_b", "session_index_a", "session_index_b",
    "category_a", "category_b", "category", "category_pair",
    "d_mm", "distance", "distance_band", "pool_threshold_mm", "admitted_by_size_term",
    "radius_expanded_only", "enrichment_band", "near_miss", "cell",
    "grid_discriminating", "selection_mode",
    "r_a_mm", "r_b_mm", "max_contour_size_mm", "contour_size_band",
    "slice_thickness_mm", "slice_thickness_band",
    "geometry_type", "assigned_stratum", "assigned_cell",
    "vote_distribution", "vote_entropy_normalized", "high_disagreement",
    "predicted_association", "model_output", "threshold_setting", "grid_setting",
    "nodule_id", "non_nodule_id", "in_repeat_subset", "primary_review_item_id",
})

REVIEWER_COLUMNS = ("review_item_id", "display_order", "round")


def opaque_id(pair_id: str, seed: int, round_name: str) -> str:
    """Opaque, stable review identifier. Round-specific, so the repeat round cannot be
    linked to the primary round by the reviewer."""
    return hashlib.sha256(f"{seed}|{round_name}|{pair_id}".encode()).hexdigest()[:20]


def _stable_rng(*parts) -> "object":
    import numpy as np
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def choose_pair_for_patient(pairs: list[Pair], seed: int) -> Pair:
    """Within-cell pair choice: seeded per patient, so one patient's draw cannot shift
    another's, and re-running a single patient is reproducible in isolation.

    `pairs` are the patient's pairs **in the assigned cell**, so they already share an
    enrichment band and the draw is uniform. The 2x near-miss weighting used at
    `0.2.0-draft` is removed: near-miss enrichment is now an exact quota on the six joint
    cells (protocol 4.6.3), and keeping a within-patient weight on top of it would enrich
    twice by an amount nobody declared.
    """
    ordered = sorted(pairs, key=lambda p: p.pair_id)
    rng = _stable_rng(seed, "pair", ordered[0].patient_id)
    return ordered[int(rng.integers(len(ordered)))]


def select_mandatory_pins(pool: list[Pair]) -> tuple[dict[str, Pair], list[Pair]]:
    """Radius-expanded-only pairs that must be covered (protocol 4.6.4).

    Every such pair must reach human review. At most one can enter the primary set per
    patient, because the primary set is one pair per patient; where a patient contributes
    several, the lowest `pair_id` is pinned and the rest are deferred to the supplemental
    census. `pair_id` is a hash of the two mark IDs, so the tie-break is deterministic,
    independent of geometry, and cannot be steered by any outcome.

    Returns (patient_id -> pinned pair, deferred pairs).
    """
    ordered = sorted((p for p in pool if p.radius_expanded_only), key=lambda p: p.pair_id)
    pins: dict[str, Pair] = {}
    deferred: list[Pair] = []
    for pair in ordered:
        if pair.patient_id in pins:
            deferred.append(pair)
        else:
            pins[pair.patient_id] = pair
    return pins, deferred


def canonical_hash(rows: list[dict], columns: tuple[str, ...]) -> str:
    """Hash over a field-ordered, row-sorted serialisation -- invariant to input order."""
    payload = json.dumps(
        [[str(r[c]) for c in columns] for r in sorted(rows, key=lambda r: r[columns[0]])],
        separators=(",", ":"), sort_keys=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class BuiltManifest:
    reviewer_rows: list[dict]
    private_rows: list[dict]
    matching_proof: dict
    reviewer_hash: str
    private_hash: str
    composition: dict
    deferred_radius_expanded: list[Pair]


def _private_row(chosen: Pair, cell: str, selection_mode: str) -> dict:
    return {
        "pair_id": chosen.pair_id,
        "patient_id": chosen.patient_id,
        "study_uid": chosen.study_uid,
        "series_uid": chosen.series_uid,
        "mark_id_a": chosen.mark_id_a,
        "mark_id_b": chosen.mark_id_b,
        "session_index_a": chosen.session_index_a,
        "session_index_b": chosen.session_index_b,
        "geometry_type": chosen.geometry_type,
        "assigned_cell": cell,
        "selection_mode": selection_mode,
        "d_mm": round(chosen.d_mm, 6),
        "r_a_mm": round(chosen.r_a_mm, 6),
        "r_b_mm": round(chosen.r_b_mm, 6),
        "pool_threshold_mm": round(chosen.pool_threshold_mm, 6),
        "radius_expanded_only": chosen.radius_expanded_only,
        "distance_band": distance_band(chosen.d_mm),
        "enrichment_band": enrichment_band(chosen.d_mm),
        "near_miss": is_near_miss(chosen.d_mm),
        "grid_discriminating": is_grid_discriminating(chosen),
        "max_contour_size_mm": round(chosen.max_contour_size_mm, 6),
        "contour_size_band": contour_size_band(chosen.max_contour_size_mm),
        "slice_thickness_mm": chosen.slice_thickness_mm,
        "slice_thickness_band": thickness_band(chosen.slice_thickness_mm),
        "category_a": chosen.category_a,
        "category_b": chosen.category_b,
    }


def build_primary_manifest(pool: list[Pair], seed: int, seed_order: int) -> BuiltManifest:
    """Solve the joint assignment exactly, pick one pair each, then blind and order.

    Mandatory-coverage pairs (radius-expanded-only) are pinned into the solve rather than
    added afterwards, so they consume quota and the feasibility proof covers them.
    """
    from collections import Counter, defaultdict

    by_patient_cell: dict[str, dict[str, list[Pair]]] = defaultdict(lambda: defaultdict(list))
    for p in pool:
        by_patient_cell[p.patient_id][cell_of(p)].append(p)
    availability = {pid: set(d) for pid, d in by_patient_cell.items()}

    pins, deferred = select_mandatory_pins(pool)
    pinned_cells = {pid: cell_of(pair) for pid, pair in pins.items()}

    match = assign_patients(availability, seed, CELL_QUOTAS, pinned_cells)
    if not match.feasible:
        raise RuntimeError(match.failure_reason)

    chosen_by_patient: dict[str, tuple[Pair, str, str]] = {
        pid: (pair, pinned_cells[pid], "mandatory_radius_expanded")
        for pid, pair in pins.items()
    }
    for patient_id, cell in match.assignment.items():
        chosen_by_patient[patient_id] = (
            choose_pair_for_patient(by_patient_cell[patient_id][cell], seed), cell, "sampled")

    private_rows = [
        _private_row(*chosen_by_patient[pid])
        for pid in sorted(chosen_by_patient, key=lambda p: (patient_priority(p, seed), p))
    ]

    if len(private_rows) != N_PRIMARY:
        raise RuntimeError(f"expected {N_PRIMARY} rows, built {len(private_rows)}")

    # Blind: opaque id + deterministic presentation order, drawn from a separate seed.
    for row in private_rows:
        row["review_item_id"] = opaque_id(row["pair_id"], seed, "primary")
    rng = _stable_rng(seed_order, "display", "primary")
    order = list(rng.permutation(len(private_rows)))
    for pos, idx in enumerate(order):
        private_rows[idx]["display_order"] = pos

    reviewer_rows = [
        {"review_item_id": r["review_item_id"], "display_order": r["display_order"],
         "round": "primary"}
        for r in private_rows
    ]

    near = [r for r in private_rows if r["near_miss"]]
    composition = {
        "n_primary": len(private_rows),
        "by_cell": dict(Counter(r["assigned_cell"] for r in private_rows)),
        "by_pair_type": dict(Counter(r["geometry_type"] for r in private_rows)),
        "by_enrichment_band": dict(Counter(r["enrichment_band"] for r in private_rows)),
        "near_miss_total": len(near),
        "near_miss_by_pair_type": dict(Counter(r["geometry_type"] for r in near)),
        "near_miss_fraction": round(len(near) / len(private_rows), 4),
        "distinct_patients": len({r["patient_id"] for r in private_rows}),
        "by_distance_band": dict(Counter(r["distance_band"] for r in private_rows)),
        "pair_type_x_distance_band": {
            f"{gt}|{db}": n for (gt, db), n in sorted(
                Counter((r["geometry_type"], r["distance_band"]) for r in private_rows).items())
        },
        "by_thickness_band": dict(Counter(r["slice_thickness_band"] for r in private_rows)),
        "by_contour_size_band": dict(Counter(r["contour_size_band"] for r in private_rows)),
        "by_category_combination": dict(Counter(
            "+".join(sorted((r["category_a"], r["category_b"]))) for r in private_rows)),
        "grid_discriminating": sum(1 for r in private_rows if r["grid_discriminating"]),
        "radius_expanded_only_in_primary": sum(
            1 for r in private_rows if r["radius_expanded_only"]),
        "radius_expanded_only_deferred_to_census": len(deferred),
        "selection_mode_counts": dict(Counter(r["selection_mode"] for r in private_rows)),
    }
    return BuiltManifest(
        reviewer_rows=reviewer_rows,
        private_rows=private_rows,
        matching_proof=match.proof(),
        reviewer_hash=canonical_hash(reviewer_rows, REVIEWER_COLUMNS),
        private_hash=canonical_hash(private_rows, ("pair_id",)),
        composition=composition,
        deferred_radius_expanded=deferred,
    )


def build_repeat_subset(private_rows: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    """Preselect the 120-item repeat subset BEFORE any label exists.

    Stratified by pair type and distance/enrichment stratum, deterministic, and identified
    through NEW opaque ids so the reviewer cannot recognise a repeat. Linkable to primary
    items only through the private mapping.
    """
    from collections import defaultdict

    strata: dict[str, list[dict]] = defaultdict(list)
    for row in private_rows:
        strata[row["assigned_cell"]].append(row)

    total = len(private_rows)
    keys = sorted(strata)
    # proportional allocation, largest-remainder, deterministic
    exact = {k: N_REPEAT * len(strata[k]) / total for k in keys}
    alloc = {k: int(exact[k]) for k in keys}
    for k in sorted(keys, key=lambda k: (-(exact[k] - alloc[k]), k)):
        if sum(alloc.values()) >= N_REPEAT:
            break
        alloc[k] += 1

    picked: list[dict] = []
    for k in keys:
        candidates = sorted(strata[k], key=lambda r: r["pair_id"])
        rng = _stable_rng(seed, "repeat", k)
        take = min(alloc[k], len(candidates))
        for i in rng.permutation(len(candidates))[:take]:
            picked.append(candidates[int(i)])

    private_map: list[dict] = []
    for row in picked:
        private_map.append({
            "repeat_item_id": opaque_id(row["pair_id"], seed, "repeat"),
            "independent_item_id": opaque_id(row["pair_id"], seed, "independent"),
            "primary_review_item_id": row["review_item_id"],
            "pair_id": row["pair_id"],
            "patient_id": row["patient_id"],
            "geometry_type": row["geometry_type"],
            "assigned_cell": row["assigned_cell"],
            "near_miss": row["near_miss"],
        })
    rng = _stable_rng(seed, "display", "repeat")
    order = list(rng.permutation(len(private_map)))
    for pos, idx in enumerate(order):
        private_map[idx]["display_order"] = pos

    reviewer_rows = [
        {"review_item_id": m["repeat_item_id"], "display_order": m["display_order"],
         "round": "repeat"}
        for m in private_map
    ]
    return reviewer_rows, private_map


def build_independent_manifest(repeat_private: list[dict], seed_order: int) -> list[dict]:
    """The same 120 items, re-blinded and re-ordered for an independent second reviewer.

    A separate opaque id and a separate presentation order, so the second reviewer's items
    cannot be aligned with the first reviewer's by identifier or by position. The subset is
    deliberately identical: the independent round is an external reproducibility audit of
    the intra-rater subset, not a second sample and not an adjudication of the primary
    labels (protocol 4.6.6).
    """
    rows = [{"review_item_id": m["independent_item_id"]} for m in repeat_private]
    rng = _stable_rng(seed_order, "display", "independent")
    order = list(rng.permutation(len(rows)))
    for pos, idx in enumerate(order):
        rows[idx]["display_order"] = pos
        rows[idx]["round"] = "independent"
    return rows


def build_census_manifest(
    deferred: list[Pair], primary_rows: list[dict], seed: int, seed_order: int,
) -> tuple[list[dict], list[dict]]:
    """Supplemental blinded census of radius-expanded-only pairs (protocol 4.6.4).

    Contains exactly the radius-expanded-only pairs that could not enter the primary 600
    because their patient already contributes one. Pairs already present in the primary
    set are deduplicated out, so every radius-expanded-only pair is reviewed exactly once
    across the two manifests.

    Census results are kept **separate** from the primary Wilson precision calculation:
    these pairs are not one-per-patient and are not a random sample, so folding them into
    the primary interval would break the patient-independence criterion (protocol 4.7).
    """
    already = {r["pair_id"] for r in primary_rows}
    unique = sorted({p.pair_id: p for p in deferred if p.pair_id not in already}.values(),
                    key=lambda p: p.pair_id)

    private_map = [_private_row(p, cell_of(p), "census_radius_expanded") for p in unique]
    for row in private_map:
        row["review_item_id"] = opaque_id(row["pair_id"], seed, "radius_expanded_census")
    if private_map:
        rng = _stable_rng(seed_order, "display", "radius_expanded_census")
        for pos, idx in enumerate(rng.permutation(len(private_map))):
            private_map[int(idx)]["display_order"] = pos

    reviewer_rows = [
        {"review_item_id": r["review_item_id"], "display_order": r["display_order"],
         "round": "radius_expanded_census"}
        for r in private_map
    ]
    return reviewer_rows, private_map


def audit_radius_expanded_coverage(
    pool: list[Pair], primary_rows: list[dict], census_rows: list[dict],
) -> dict:
    """Prove that every radius-expanded-only pair in the pool reaches human review."""
    expected = {p.pair_id for p in pool if p.radius_expanded_only}
    in_primary = {r["pair_id"] for r in primary_rows if r["radius_expanded_only"]}
    in_census = {r["pair_id"] for r in census_rows}
    covered = in_primary | in_census
    return {
        "radius_expanded_only_in_pool": len(expected),
        "in_primary_manifest": sorted(in_primary),
        "in_census_manifest": sorted(in_census),
        "overlap_primary_census": sorted(in_primary & in_census),
        "missing": sorted(expected - covered),
        "unexpected": sorted(covered - expected),
        "distinct_patients": len({
            r["patient_id"] for r in primary_rows if r["radius_expanded_only"]
        } | {r["patient_id"] for r in census_rows}),
        "census_required": bool(in_census),
        "pass": covered == expected and not (in_primary & in_census),
    }


def audit_blinding(rows: list[dict]) -> dict:
    """Assert a reviewer-facing manifest exposes no forbidden field."""
    present = set()
    for row in rows:
        present |= set(row)
    leaked = sorted(present & FORBIDDEN_REVIEWER_FIELDS)
    unexpected = sorted(present - set(REVIEWER_COLUMNS))
    return {
        "columns_present": sorted(present),
        "allowed_columns": list(REVIEWER_COLUMNS),
        "forbidden_fields_leaked": leaked,
        "unexpected_columns": unexpected,
        "pass": not leaked and not unexpected,
    }


def _git(*args: str) -> str:
    try:
        return subprocess.run(("git", *args), capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                              check=True).stdout.strip()
    except Exception:
        return "unavailable"


def worktree_hash(paths: list[str]) -> str:
    """Hash of the pilot source files actually used, so a manifest is traceable to code."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(os.path.basename(p).encode())
        with open(p, "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()


def build_provenance(*, split_id: str, seed: int, seed_order: int,
                     outputs: dict[str, str], source_files: list[str],
                     pool_summary: dict, extraction_summary: dict) -> dict:
    """Provenance record. Contains no patient names and no model results."""
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "xml_archive_sha256": CORPUS_SHA256,
        "development_split_id": split_id,
        "protocol_commit": _git("rev-parse", "HEAD"),
        "protocol_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "code_worktree_hash": worktree_hash(source_files),
        "code_dirty": _git("status", "--porcelain") != "",
        "seeds": {"sampling": seed, "display_order": seed_order},
        "algorithm_versions": {
            "extraction": EXTRACTION_VERSION,
            "geometry": GEOMETRY_VERSION,
            "pool": POOL_VERSION,
            "matching": MATCHING_VERSION,
            "manifest": MANIFEST_VERSION,
            "repeat_manifest": REPEAT_MANIFEST_VERSION,
            "census_manifest": CENSUS_MANIFEST_VERSION,
        },
        "quotas": {
            "joint_cells": CELL_QUOTAS,
            "pair_type_totals": PAIR_TYPE_QUOTAS,
            "near_miss_total": sum(
                v for k, v in CELL_QUOTAS.items() if k.endswith("|near_miss")),
        },
        "output_hashes": outputs,
        "extraction_counts": extraction_summary,
        "pool_summary": pool_summary,
        "contains_patient_names": False,
        "contains_model_results": False,
        "geometry_limitation": (
            "Mark centres are millimetre offsets in a per-series frame (PixelSpacing-scaled "
            "pixel indices; z from imageZposition). The DICOM ImagePositionPatient origin is "
            "not applied. Valid because every pilot distance is a within-series difference, "
            "for which a constant origin cancels. The production parser must use the full "
            "index-to-world transform."
        ),
    }


def write_csv(path: str, rows: list[dict], columns: tuple[str, ...]) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: r[columns[0]]):
            writer.writerow(row)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write_json(path: str, payload: dict) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
