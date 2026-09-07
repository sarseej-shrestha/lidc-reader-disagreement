"""Frozen eligible-pair pool predicate for the association pilot.

Predicate (docs/protocol.md 4.6.1), frozen:

    a cross-session pair (i, j) is eligible  <=>  d(i,j) <= max(12 mm, r_i + r_j)

with d the Euclidean distance between physical mark centres, r the volume-equivalent
spherical radius for contour marks, and r = 0 for point marks.

The pool is a strict superset of every pair any grid setting could merge (max grid
threshold is max(6 mm, r_i + r_j)); the 12 mm floor supplies adversarial near-miss
negatives that no setting merges.

The predicate is conjunctive on distance. The r_i + r_j term raises the bound only for
pairs whose marks are physically large -- it does NOT admit every pair containing a large
contour regardless of distance.

Category, reader agreement, and model output play no part in pool construction. Mark
category is carried on the record for *reporting* strata only and is never an input to
eligibility. This holds for `ambiguous_unresolved` marks too: they are excluded from the
downstream benchmark label space, but association is a physical question that can be
decided without a category, so excluding them here would make association depend on
category. `test_ambiguous_category_does_not_alter_pool_eligibility` is the regression.

Two derived quantities are defined here because the sampling design depends on them:

  * the **near-miss band** ``2.0 mm <= d(i,j) <= 10.0 mm`` -- the band that discriminates
    between grid settings, and now an exact quota rather than a sampling weight;
  * **radius-expanded-only** pairs -- admitted solely because ``r_i + r_j > 12 mm`` and
    ``12 mm < d(i,j) <= r_i + r_j``. Every one of them must reach human review, or the
    claim that the size-expanded predicate prevents unscored large-alpha merges is false.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

from .xml_extract import Mark

POOL_FLOOR_MM = 12.0
POOL_VERSION = "pool-predicate-v2"

#: Largest tolerance any grid setting can produce: max(tau_floor) = 6 mm, alpha_max = 1.0
MAX_GRID_TAU_FLOOR_MM = 6.0

#: Near-miss band, protocol 4.6.3, frozen at 0.2.1-draft: 2.0 mm <= d(i,j) <= 10.0 mm,
#: inclusive at both ends. This is the band that discriminates between grid settings, and
#: it is now an exact sampling quota rather than a within-patient weight.
NEAR_MISS_MIN_MM = 2.0
NEAR_MISS_MAX_MM = 10.0

#: The proposed threshold grid (protocol 4.5). Used ONLY to count how many sampled pairs
#: the grid settings disagree about -- a purely geometric design diagnostic computed with
#: no labels, no model, and no performance measure.
GRID_ALPHAS = (0.0, 0.5, 1.0)
GRID_TAU_FLOORS_MM = (2.0, 3.0, 4.0, 5.0, 6.0)


@dataclass(frozen=True)
class Pair:
    pair_id: str
    patient_id: str
    study_uid: str
    series_uid: str
    mark_id_a: str
    mark_id_b: str
    session_index_a: int
    session_index_b: int
    geometry_type: str          # point-point | point-contour | contour-contour
    d_mm: float
    r_a_mm: float
    r_b_mm: float
    pool_threshold_mm: float
    radius_expanded_only: bool
    category_a: str             # reporting only; never an eligibility input
    category_b: str
    max_contour_size_mm: float
    slice_thickness_mm: float


def distance_mm(a: Mark, b: Mark) -> float:
    return ((a.x_mm - b.x_mm) ** 2 + (a.y_mm - b.y_mm) ** 2 + (a.z_mm - b.z_mm) ** 2) ** 0.5


def pool_threshold_mm(a: Mark, b: Mark) -> float:
    return max(POOL_FLOOR_MM, a.radius_mm + b.radius_mm)


def is_eligible(a: Mark, b: Mark) -> bool:
    """The frozen predicate. Same series, different reading sessions, distance bound."""
    if a.series_uid != b.series_uid:
        return False                      # never pair across series or timepoints
    if a.session_index == b.session_index:
        return False                      # same reader is never a pair
    return distance_mm(a, b) <= pool_threshold_mm(a, b)


def is_radius_expanded_only(d_mm: float, r_a_mm: float, r_b_mm: float) -> bool:
    """True iff the pair is admitted *only* by the size term of the pool predicate.

    Both conditions are required and are stated separately rather than inferred:

        r_i + r_j > 12 mm          the size term is what raised the bound, and
        12 mm < d(i,j) <= r_i + r_j the pair would otherwise have been excluded

    These are the pairs that make the precision denominator correct: without them a
    large-alpha grid setting could merge a pair the reference set never considered.
    """
    return (r_a_mm + r_b_mm) > POOL_FLOOR_MM and POOL_FLOOR_MM < d_mm <= (r_a_mm + r_b_mm)


def geometry_type(a: Mark, b: Mark) -> str:
    kinds = (a.kind, b.kind)
    if kinds == ("point", "point"):
        return "point-point"
    if kinds == ("contour", "contour"):
        return "contour-contour"
    return "point-contour"


def pair_id(mark_id_a: str, mark_id_b: str) -> str:
    """Order-independent stable pair identifier."""
    import hashlib
    lo, hi = sorted((mark_id_a, mark_id_b))
    return hashlib.sha256(f"{lo}|{hi}".encode()).hexdigest()[:16]


def build_pool(
    marks_by_series: dict[str, tuple[str, str, Sequence[Mark], float]],
) -> list[Pair]:
    """Enumerate the eligible pool.

    `marks_by_series` maps series_uid -> (patient_id, study_uid, marks, slice_thickness_mm).
    Marks are sorted by mark_id before pairing so the output order does not depend on
    filesystem or XML input ordering.
    """
    pairs: list[Pair] = []
    for series_uid in sorted(marks_by_series):
        patient_id, study_uid, marks, thickness = marks_by_series[series_uid]
        ordered = sorted(marks, key=lambda m: m.mark_id)
        for a, b in combinations(ordered, 2):
            if not is_eligible(a, b):
                continue
            lo, hi = (a, b) if a.mark_id <= b.mark_id else (b, a)
            d = distance_mm(lo, hi)
            thr = pool_threshold_mm(lo, hi)
            pairs.append(Pair(
                pair_id=pair_id(lo.mark_id, hi.mark_id),
                patient_id=patient_id, study_uid=study_uid, series_uid=series_uid,
                mark_id_a=lo.mark_id, mark_id_b=hi.mark_id,
                session_index_a=lo.session_index, session_index_b=hi.session_index,
                geometry_type=geometry_type(lo, hi),
                d_mm=d, r_a_mm=lo.radius_mm, r_b_mm=hi.radius_mm,
                pool_threshold_mm=thr,
                radius_expanded_only=is_radius_expanded_only(d, lo.radius_mm, hi.radius_mm),
                category_a=lo.category, category_b=hi.category,
                max_contour_size_mm=max(2 * lo.radius_mm, 2 * hi.radius_mm),
                slice_thickness_mm=thickness,
            ))
    pairs.sort(key=lambda p: p.pair_id)
    return pairs


def distance_band(d_mm: float) -> str:
    for hi, label in ((2, "[0,2)"), (4, "[2,4)"), (6, "[4,6)"), (8, "[6,8)"), (10, "[8,10)")):
        if d_mm < hi:
            return label
    return "[10,12]" if d_mm <= POOL_FLOOR_MM else "(12,inf) size-admitted"


def contour_size_band(size_mm: float) -> str:
    if size_mm == 0:
        return "n/a (point only)"
    if size_mm < 6:
        return "<6mm"
    if size_mm < 10:
        return "6-10mm"
    if size_mm < 20:
        return "10-20mm"
    return ">=20mm"


def thickness_band(t_mm: float) -> str:
    if t_mm <= 1.25:
        return "<=1.25"
    return "1.25-2.5" if t_mm <= 2.5 else ">2.5"


def is_near_miss(d_mm: float) -> bool:
    """The near-miss band, inclusive at both ends: 2.0 mm <= d <= 10.0 mm."""
    return NEAR_MISS_MIN_MM <= d_mm <= NEAR_MISS_MAX_MM


def enrichment_band(d_mm: float) -> str:
    return "near_miss" if is_near_miss(d_mm) else "other"


def cell_of(pair: Pair) -> str:
    """The joint sampling cell: pair type crossed with the enrichment band.

    Sampling quotas are defined on these six cells jointly, so the pair-type totals and
    the near-miss totals are satisfied by one matching rather than by generating strata
    independently and repairing collisions afterwards.
    """
    return f"{pair.geometry_type}|{enrichment_band(pair.d_mm)}"


def grid_merge_predictions(pair: Pair) -> dict[str, bool]:
    """Merge decision of every proposed grid setting for one pair.

    tau(i,j) = max(tau_floor, alpha * (r_i + r_j)); merge iff d(i,j) <= tau(i,j).
    Geometry only -- no label, no model, no performance quantity is involved.
    """
    r_sum = pair.r_a_mm + pair.r_b_mm
    return {
        f"alpha={a}|tau_floor={t}": pair.d_mm <= max(t, a * r_sum)
        for a in GRID_ALPHAS for t in GRID_TAU_FLOORS_MM
    }


def is_grid_discriminating(pair: Pair) -> bool:
    """True iff the 15 proposed settings do not all agree about this pair.

    A pair every setting merges (or every setting splits) carries no information about
    which setting to prefer; these are the pairs that do.
    """
    return len(set(grid_merge_predictions(pair).values())) > 1


def summarise_pool(pairs: Iterable[Pair]) -> dict:
    from collections import Counter
    pairs = list(pairs)
    by_cat = Counter("+".join(sorted((p.category_a, p.category_b))) for p in pairs)
    return {
        "total": len(pairs),
        "radius_expanded_only": sum(1 for p in pairs if p.radius_expanded_only),
        "by_pair_type": dict(Counter(p.geometry_type for p in pairs)),
        "by_distance_band": dict(Counter(distance_band(p.d_mm) for p in pairs)),
        "by_enrichment_band": dict(Counter(enrichment_band(p.d_mm) for p in pairs)),
        "by_cell": dict(Counter(cell_of(p) for p in pairs)),
        "by_category_combination": dict(by_cat),
        "by_contour_size_band": dict(Counter(contour_size_band(p.max_contour_size_mm) for p in pairs)),
        "by_thickness_band": dict(Counter(thickness_band(p.slice_thickness_mm) for p in pairs)),
        "pair_type_x_distance_band": {
            f"{gt}|{db}": n for (gt, db), n in sorted(
                Counter((p.geometry_type, distance_band(p.d_mm)) for p in pairs).items())
        },
        "grid_discriminating": sum(1 for p in pairs if is_grid_discriminating(p)),
        "patients_with_pairs": len({p.patient_id for p in pairs}),
        "patients_per_cell": {
            c: len({p.patient_id for p in pairs if cell_of(p) == c})
            for c in sorted({cell_of(p) for p in pairs})
        },
    }


#: Frozen expectations (protocol 4.6.2, verified 2026-08-31).
EXPECTED_POOL = {
    "total": 44668,
    "radius_expanded_only": 10,
    "by_pair_type": {"point-point": 34350, "contour-contour": 6238, "point-contour": 4080},
    "patients_with_pairs": 830,
}


class PoolReconciliationError(RuntimeError):
    pass


def assert_pool_reconciled(summary: dict) -> None:
    problems = []
    for key in ("total", "radius_expanded_only", "patients_with_pairs"):
        if summary[key] != EXPECTED_POOL[key]:
            problems.append(f"  {key}: expected {EXPECTED_POOL[key]}, observed {summary[key]}")
    for gt, want in EXPECTED_POOL["by_pair_type"].items():
        got = summary["by_pair_type"].get(gt)
        if got != want:
            problems.append(f"  by_pair_type[{gt}]: expected {want}, observed {got}")
    if problems:
        raise PoolReconciliationError(
            "pool reconciliation FAILED -- refusing to generate a manifest:\n" + "\n".join(problems)
        )
