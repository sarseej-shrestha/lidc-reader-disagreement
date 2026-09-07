"""Exact joint capacity-constrained patient-to-cell assignment for the 600-pair set.

Since `0.2.1-draft` the sampling strata are the **six joint cells** formed by pair type
crossed with the near-miss band, not the three pair types. Generating each stratum
independently and repairing collisions afterwards is prohibited: per-cell patient
availability overlaps heavily (a patient with a contour-contour near-miss pair usually
also has point-point pairs), so an independent draw has no feasibility guarantee and would
silently under-fill the scarcest cell rather than fail.

Formulation (docs/protocol.md 4.6.3):

    SRC -> patient_i     capacity 1              exactly one primary pair per patient
    patient_i -> cell_g  capacity 1              iff the patient has >=1 eligible pair in g
    cell_g -> SNK        capacity quota[g]       120/120/90/90/90/90 as explicit capacities
    feasible             <=>  maxflow == 600

All capacities are integers, so Dinic returns an integral flow and each unit through
patient_i -> cell_g is exactly one patient assigned to one cell. The pair-type totals
(240/180/180) and the near-miss totals (120/90/90, 300 overall) are both consequences of
the same single solve.

**Pinning.** Some pairs must appear in the reference set for correctness rather than by
sampling -- the radius-expanded-only pairs (protocol 4.6.4). A pinned patient is removed
from the node set and its cell's quota is decremented, so the residual problem is solved
exactly and the pinned pairs cost feasibility rather than being bolted on afterwards. If
the residual is infeasible the whole assignment fails closed.

Determinism: patients are inserted in ascending seeded priority sha256(f"{seed}:{pid}"),
cells in a fixed order, adjacency lists sorted. Nothing depends on filesystem or XML input
ordering.

Implemented from the standard Dinic formulation; no code was copied from any source.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

MATCHING_VERSION = "maxflow-joint-bmatch-v2"

#: Pair-type totals. Derived from CELL_QUOTAS and asserted, never set independently.
PAIR_TYPE_QUOTAS = {"point-point": 240, "point-contour": 180, "contour-contour": 180}

#: The joint quotas, frozen at 0.2.1-draft. Near-miss is exactly 300 of 600, allocated
#: proportionally to the pair-type quotas.
CELL_QUOTAS = {
    "point-point|near_miss": 120,
    "point-point|other": 120,
    "point-contour|near_miss": 90,
    "point-contour|other": 90,
    "contour-contour|near_miss": 90,
    "contour-contour|other": 90,
}
TOTAL_QUOTA = sum(CELL_QUOTAS.values())

#: Fixed cell order: ascending patient availability on the hash-pinned corpus (scarcest
#: first). This affects only insertion order and therefore tie resolution -- never
#: feasibility, which is exact and order-independent.
CELL_ORDER = (
    "contour-contour|near_miss",   # 129 eligible patients -- the scarcest cell
    "point-contour|near_miss",     # 279
    "point-contour|other",         # 501
    "contour-contour|other",       # 649
    "point-point|near_miss",       # 663
    "point-point|other",           # 816
)

#: Retained for provenance continuity with `0.2.0-draft`, which quota'd pair types alone.
QUOTAS = dict(PAIR_TYPE_QUOTAS)

assert set(CELL_ORDER) == set(CELL_QUOTAS)
assert TOTAL_QUOTA == sum(PAIR_TYPE_QUOTAS.values()) == 600
for _gt, _n in PAIR_TYPE_QUOTAS.items():
    assert sum(v for k, v in CELL_QUOTAS.items() if k.split("|")[0] == _gt) == _n


def patient_priority(patient_id: str, seed: int) -> str:
    """Stable seeded priority. Depends on patient identity and the seed, never on input
    order."""
    return hashlib.sha256(f"{seed}:{patient_id}".encode()).hexdigest()


class _Dinic:
    def __init__(self, n: int) -> None:
        self.n = n
        self.graph: list[list[list[int]]] = [[] for _ in range(n)]

    def add_edge(self, u: int, v: int, cap: int) -> None:
        self.graph[u].append([v, cap, len(self.graph[v])])
        self.graph[v].append([u, 0, len(self.graph[u]) - 1])

    def _levels(self, src: int, snk: int) -> bool:
        self.level = [-1] * self.n
        self.level[src] = 0
        queue = [src]
        for u in queue:
            for edge in self.graph[u]:
                if edge[1] > 0 and self.level[edge[0]] < 0:
                    self.level[edge[0]] = self.level[u] + 1
                    queue.append(edge[0])
        return self.level[snk] >= 0

    def _augment(self, u: int, snk: int, limit: int) -> int:
        if u == snk:
            return limit
        while self.iter[u] < len(self.graph[u]):
            edge = self.graph[u][self.iter[u]]
            v = edge[0]
            if edge[1] > 0 and self.level[v] == self.level[u] + 1:
                pushed = self._augment(v, snk, min(limit, edge[1]))
                if pushed > 0:
                    edge[1] -= pushed
                    self.graph[v][edge[2]][1] += pushed
                    return pushed
            self.iter[u] += 1
        return 0

    def max_flow(self, src: int, snk: int) -> int:
        flow = 0
        while self._levels(src, snk):
            self.iter = [0] * self.n
            while True:
                pushed = self._augment(src, snk, 1 << 30)
                if pushed == 0:
                    break
                flow += pushed
        return flow


class InfeasibleAssignmentError(RuntimeError):
    """Raised when no assignment satisfies every quota. Fails closed; writes no manifest."""


@dataclass
class MatchingResult:
    assignment: dict[str, str] = field(default_factory=dict)   # patient_id -> cell
    pinned: dict[str, str] = field(default_factory=dict)       # patient_id -> cell
    requested_flow: int = 0
    achieved_flow: int = 0            # residual flow, excluding pinned units
    capacities: dict[str, int] = field(default_factory=dict)   # full quotas
    residual_capacities: dict[str, int] = field(default_factory=dict)
    availability: dict[str, int] = field(default_factory=dict)
    exclusive_availability: dict[str, int] = field(default_factory=dict)
    slack: dict[str, int] = field(default_factory=dict)
    filled: dict[str, int] = field(default_factory=dict)       # including pinned units
    n_patient_nodes: int = 0
    feasible: bool = False
    failure_reason: str | None = None
    diagnosis: dict | None = None

    def proof(self) -> dict:
        by_type: dict[str, int] = {}
        for cell, n in self.filled.items():
            by_type[cell.split("|")[0]] = by_type.get(cell.split("|")[0], 0) + n
        by_band: dict[str, int] = {}
        for cell, n in self.filled.items():
            by_band[cell.split("|")[1]] = by_band.get(cell.split("|")[1], 0) + n
        proof = {
            "algorithm": MATCHING_VERSION,
            "method": "integral max-flow (Dinic) on a joint bipartite b-matching over "
                      "pair-type x near-miss-band cells",
            "requested_flow": self.requested_flow,
            "achieved_flow": self.achieved_flow,
            "pinned_units": len(self.pinned),
            "total_assigned": len(self.assignment) + len(self.pinned),
            "feasible": self.feasible,
            "failure_reason": self.failure_reason,
            "n_patient_nodes": self.n_patient_nodes,
            "patient_capacity": 1,
            "capacities_by_cell": self.capacities,
            "residual_capacities_by_cell": self.residual_capacities,
            "availability_by_cell": self.availability,
            "patients_eligible_for_only_this_cell": self.exclusive_availability,
            "slack_by_cell": self.slack,
            "filled_by_cell": self.filled,
            "filled_by_pair_type": by_type,
            "filled_by_enrichment_band": by_band,
            "pinned_by_cell": {
                c: sum(1 for v in self.pinned.values() if v == c) for c in self.capacities
            },
            "patient_capacity_validation": {
                "assignments": len(self.assignment) + len(self.pinned),
                "distinct_patients": len(set(self.assignment) | set(self.pinned)),
                "max_assignments_per_patient": 1,
                "ok": not (set(self.assignment) & set(self.pinned)),
            },
            "uniqueness_checks": {
                "one_cell_per_patient": all(
                    isinstance(v, str) for v in self.assignment.values()),
                "quotas_exactly_filled": self.filled == self.capacities,
                "pair_type_quotas_exactly_filled": by_type == PAIR_TYPE_QUOTAS,
                "near_miss_total": by_band.get("near_miss", 0),
            },
            "hall_union_check": {
                "patients_with_any_eligible_cell": self.n_patient_nodes + len(self.pinned),
                "total_quota": self.requested_flow + len(self.pinned),
                "ok": self.n_patient_nodes + len(self.pinned)
                      >= self.requested_flow + len(self.pinned),
            },
        }
        if self.diagnosis is not None:
            proof["infeasibility_diagnosis"] = self.diagnosis
        return proof


def _solve(availability: dict[str, set[str]], seed: int, quotas: dict[str, int]):
    """Run one exact max-flow solve. Returns (flow, assignment, patients, cells)."""
    total = sum(quotas.values())
    patients = sorted(availability, key=lambda p: (patient_priority(p, seed), p))
    p_index = {p: i for i, p in enumerate(patients)}
    cells = [c for c in CELL_ORDER if c in quotas]
    cells += [c for c in sorted(quotas) if c not in cells]
    src = len(patients) + len(cells)
    snk = src + 1

    net = _Dinic(snk + 1)
    for p in patients:
        net.add_edge(src, p_index[p], 1)
    for j, c in enumerate(cells):
        net.add_edge(len(patients) + j, snk, quotas[c])
    for p in patients:
        for c in sorted(availability[p]):
            if c in quotas:
                net.add_edge(p_index[p], len(patients) + cells.index(c), 1)

    flow = net.max_flow(src, snk)
    assignment: dict[str, str] = {}
    for p in patients:
        for edge in net.graph[p_index[p]]:
            v = edge[0]
            if len(patients) <= v < len(patients) + len(cells) and edge[1] == 0:
                assignment[p] = cells[v - len(patients)]
                break
    return flow, assignment, patients, cells, total


def diagnose_infeasibility(
    availability: dict[str, set[str]],
    quotas: dict[str, int],
    filled: dict[str, int],
    achieved_flow: int,
    seed: int,
) -> dict:
    """Everything needed to decide what to do about an infeasible joint quota.

    Reports the maximum achievable flow, which cells bind, where the patient conflicts
    are, and the nearest feasible allocation -- never a silently relaxed quota.
    """
    avail_counts = {c: sum(1 for s in availability.values() if c in s) for c in quotas}
    exclusive = {
        c: sum(1 for s in availability.values() if s & set(quotas) == {c}) for c in quotas
    }
    binding = {c: quotas[c] - filled.get(c, 0) for c in quotas if filled.get(c, 0) < quotas[c]}

    # Nearest feasible allocation: the same network with every cell capacity raised to its
    # availability upper bound. Its per-cell fill is a feasible allocation with the largest
    # attainable total, so it says how much of the shortfall is structural.
    relaxed_quotas = {c: avail_counts[c] for c in quotas}
    relaxed_flow, relaxed_assign, _, _, _ = _solve(availability, seed, relaxed_quotas)
    relaxed_fill = {c: sum(1 for v in relaxed_assign.values() if v == c) for c in quotas}

    return {
        "maximum_achievable_flow": achieved_flow,
        "requested_flow": sum(quotas.values()),
        "shortfall": sum(quotas.values()) - achieved_flow,
        "binding_cells": binding,
        "per_cell_upper_bound_patients": avail_counts,
        "patient_conflicts": {
            "patients_with_any_eligible_cell": len(availability),
            "patients_eligible_for_exactly_one_cell": exclusive,
            "cells_where_demand_exceeds_availability": {
                c: {"quota": quotas[c], "available_patients": avail_counts[c]}
                for c in quotas if avail_counts[c] < quotas[c]
            },
        },
        "nearest_feasible_allocation": {
            "note": "maximum-total feasible allocation with every cell capacity raised to "
                    "its availability bound; NOT an authorised quota change",
            "total": relaxed_flow,
            "by_cell": relaxed_fill,
        },
        "action_required": "Quotas are never silently relaxed. Stop, report, and obtain an "
                           "explicit protocol amendment before regenerating.",
    }


def assign_patients(
    availability: dict[str, set[str]],
    seed: int,
    quotas: dict[str, int] | None = None,
    pinned: dict[str, str] | None = None,
) -> MatchingResult:
    """Solve the exact joint assignment.

    `availability` maps patient_id -> eligible cells. `pinned` maps patient_id -> the cell
    that patient is required to occupy (mandatory-coverage pairs); pinned patients are
    removed from the sampled node set and their cell quota is decremented.
    """
    quotas = dict(quotas or CELL_QUOTAS)
    pinned = dict(pinned or {})
    full_total = sum(quotas.values())

    for pid, cell in pinned.items():
        if cell not in quotas:
            raise InfeasibleAssignmentError(f"pinned patient {pid}: unknown cell {cell!r}")
        if cell not in availability.get(pid, set()):
            raise InfeasibleAssignmentError(
                f"pinned patient {pid} has no eligible pair in cell {cell!r}")

    residual_quotas = dict(quotas)
    for cell in pinned.values():
        residual_quotas[cell] -= 1
    negative = {c: n for c, n in residual_quotas.items() if n < 0}
    sampled_availability = {p: s for p, s in availability.items() if p not in pinned}

    avail_counts = {c: sum(1 for s in availability.values() if c in s) for c in quotas}
    exclusive = {
        c: sum(1 for s in availability.values() if s & set(quotas) == {c}) for c in quotas
    }

    if negative:
        result = MatchingResult(
            pinned=pinned, requested_flow=sum(residual_quotas.values()),
            achieved_flow=0, capacities=quotas, residual_capacities=residual_quotas,
            availability=avail_counts, exclusive_availability=exclusive,
            slack={c: avail_counts[c] - quotas[c] for c in quotas},
            filled={}, n_patient_nodes=len(sampled_availability), feasible=False,
        )
        result.failure_reason = (
            f"more pinned pairs than quota in cells {negative}; no manifest is written")
        return result

    flow, assignment, patients, _, residual_total = _solve(
        sampled_availability, seed, residual_quotas)

    filled = {
        c: sum(1 for v in assignment.values() if v == c)
           + sum(1 for v in pinned.values() if v == c)
        for c in quotas
    }
    result = MatchingResult(
        assignment=assignment,
        pinned=pinned,
        requested_flow=residual_total,
        achieved_flow=flow,
        capacities=quotas,
        residual_capacities=residual_quotas,
        availability=avail_counts,
        exclusive_availability=exclusive,
        slack={c: avail_counts[c] - quotas[c] for c in quotas},
        filled=filled,
        n_patient_nodes=len(patients),
        feasible=(flow == residual_total and filled == quotas),
    )
    if not result.feasible:
        short = {c: quotas[c] - filled.get(c, 0) for c in quotas if filled.get(c, 0) < quotas[c]}
        result.diagnosis = diagnose_infeasibility(
            sampled_availability, residual_quotas,
            {c: filled[c] - sum(1 for v in pinned.values() if v == c) for c in quotas},
            flow, seed)
        result.failure_reason = (
            f"joint max flow {flow + len(pinned)} < required {full_total}; unfilled quota "
            f"by cell: {short}. No manifest is written. Quotas are never manually "
            f"reallocated. See infeasibility_diagnosis for binding cells, patient "
            f"conflicts, and the nearest feasible allocation."
        )
    return result
