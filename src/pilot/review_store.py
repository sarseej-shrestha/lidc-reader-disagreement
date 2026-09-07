"""Append-only storage for human reference labels.

Governance, enforced here rather than documented and hoped for:

  * Labels are created by PEOPLE. No model, similarity algorithm, heuristic, or generated
    description may create, suggest, prefill, or alter a label. `save_label` refuses any
    record whose `reviewer_id` is not registered as human, and there is deliberately no
    code path that produces a label from data.
  * The vocabulary is exactly three values. Anything else is rejected.
  * Records are append-only. An earlier decision is never overwritten or deleted; a
    revision is a new record and both remain visible.
  * A second primary decision on the same item by the same reviewer is refused, so an
    accidental double pass cannot silently replace a judgement.
  * No free-text field is stored, so patient-identifying text cannot be entered.
  * The intra-rater `repeat` round enforces a **seven-day washout** since that reviewer's
    last `primary` decision. Repeat answers live in their own round and never overwrite
    the primary answers.
  * Roles are explicit. Exactly one reviewer may hold the `primary_reference` role, and
    only that reviewer's `primary` labels drive the predeclared threshold-selection
    calculation. `independent` reviewers are an external reproducibility audit; the store
    keeps their labels separate and never lets them adjudicate or replace a primary label.

The primary reviewer is a **human-reviewed operational association reference**, not a
radiologist, medical expert, or clinical annotator, and their labels are not clinical
ground truth.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone

LABELS = ("same_physical_lesion", "different_physical_lesion", "indeterminate")

#: Rounds the store accepts. Anything else is refused rather than silently created.
ROUNDS = ("primary", "repeat", "independent", "radius_expanded_census")

#: Reviewer roles. Exactly one `primary_reference` reviewer is permitted.
ROLES = ("primary_reference", "independent")

#: Minimum washout before the intra-rater repeat round (protocol 4.6.6).
WASHOUT_DAYS = 7

#: Predefined reason codes. A closed vocabulary, because free text could carry identifying
#: information and cannot be audited.
REASON_CODES = (
    "clearly_one_lesion", "clearly_two_lesions", "adjacent_structures_unclear",
    "slice_gap_limits_continuity", "marks_far_apart", "image_quality_limits_judgement",
    "no_reason_given",
)

STORE_VERSION = "review-store-v1"


class LabelRejected(RuntimeError):
    pass


class ReviewStore:
    """One append-only JSONL file per (round, reviewer)."""

    def __init__(self, root: str, human_reviewers: dict[str, str] | None = None) -> None:
        self.root = root
        os.makedirs(root, exist_ok=True)
        # reviewer_id -> attestation string. Registration is a human act performed out of
        # band; this class never adds a reviewer on its own.
        self._humans = dict(human_reviewers or {})
        self._roles: dict[str, str] = {}
        self._lock = threading.Lock()

    # -- reviewer governance ------------------------------------------------------
    def register_human_reviewer(self, reviewer_id: str, attestation: str,
                                role: str = "primary_reference") -> None:
        if not reviewer_id or not attestation:
            raise LabelRejected("reviewer registration requires an id and an attestation")
        if role not in ROLES:
            raise LabelRejected(f"role must be one of {ROLES}; refused {role!r}")
        if role == "primary_reference":
            existing = [r for r, v in self._roles.items()
                        if v == "primary_reference" and r != reviewer_id]
            if existing:
                raise LabelRejected(
                    f"a primary_reference reviewer is already registered ({existing[0]}). "
                    "Exactly one reviewer's primary labels drive threshold selection; "
                    "register additional reviewers with role='independent'."
                )
        self._humans[reviewer_id] = attestation
        self._roles[reviewer_id] = role
        path = os.path.join(self.root, "reviewers.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"attestations": self._humans, "roles": self._roles},
                      fh, indent=2, sort_keys=True)

    def is_human(self, reviewer_id: str) -> bool:
        return reviewer_id in self._humans

    def role_of(self, reviewer_id: str) -> str | None:
        return self._roles.get(reviewer_id)

    def primary_reference_reviewer(self) -> str | None:
        for rid, role in sorted(self._roles.items()):
            if role == "primary_reference":
                return rid
        return None

    # -- storage -----------------------------------------------------------------
    def path_for(self, round_name: str, reviewer_id: str) -> str:
        safe = "".join(c for c in f"{round_name}__{reviewer_id}" if c.isalnum() or c in "._-")
        return os.path.join(self.root, f"labels__{safe}.jsonl")

    def read_all(self, round_name: str | None = None) -> list[dict]:
        out: list[dict] = []
        for name in sorted(os.listdir(self.root)):
            if not name.startswith("labels__") or not name.endswith(".jsonl"):
                continue
            with open(os.path.join(self.root, name), encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if round_name is None or rec.get("round") == round_name:
                        out.append(rec)
        return out

    def completed_items(self, round_name: str, reviewer_id: str) -> set[str]:
        """Items this reviewer has already decided in this round -- used to resume."""
        return {
            r["review_item_id"] for r in self.read_all(round_name)
            if r.get("reviewer_id") == reviewer_id
        }

    def save_label(
        self,
        *,
        review_item_id: str,
        reviewer_id: str,
        label: str,
        round_name: str,
        reason_code: str = "no_reason_given",
        supersedes: str | None = None,
    ) -> dict:
        if label not in LABELS:
            raise LabelRejected(
                f"label must be one of {LABELS}; refused {label!r}"
            )
        if round_name not in ROUNDS:
            raise LabelRejected(f"round must be one of {ROUNDS}; refused {round_name!r}")
        if reason_code not in REASON_CODES:
            raise LabelRejected(f"reason_code must be one of {REASON_CODES}")
        if not self.is_human(reviewer_id):
            raise LabelRejected(
                f"reviewer_id {reviewer_id!r} is not a registered human reviewer. "
                "Labels may only be created by people; no automated source is permitted."
            )
        role = self.role_of(reviewer_id)
        if round_name in ("primary", "radius_expanded_census") and role != "primary_reference":
            raise LabelRejected(
                f"round {round_name!r} is reserved for the primary_reference reviewer; "
                f"{reviewer_id!r} holds role {role!r}. An independent reviewer's labels are "
                "an external audit and never enter the primary reference."
            )
        if round_name == "repeat":
            blocked = self.washout_status(reviewer_id)
            if not blocked["satisfied"]:
                raise LabelRejected(
                    f"intra-rater repeat round requires a {WASHOUT_DAYS}-day washout; "
                    f"{blocked['days_elapsed']:.2f} days have elapsed since "
                    f"{reviewer_id!r} last decided a primary item. Refused."
                )
        with self._lock:
            already = self.completed_items(round_name, reviewer_id)
            if review_item_id in already and supersedes is None:
                raise LabelRejected(
                    f"{reviewer_id} already decided {review_item_id} in round {round_name}. "
                    "Duplicate primary reviews are refused; pass supersedes=<record_id> to "
                    "append a revision, which keeps both records visible."
                )
            record = {
                "record_id": f"{round_name}:{reviewer_id}:{review_item_id}:{len(already)}",
                "review_item_id": review_item_id,
                "reviewer_id": reviewer_id,
                "label": label,
                "round": round_name,
                "reason_code": reason_code,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "supersedes": supersedes,
                "store_version": STORE_VERSION,
                "label_source": "human",
            }
            path = self.path_for(round_name, reviewer_id)
            with open(path, "a", encoding="utf-8") as fh:      # append-only
                fh.write(json.dumps(record, sort_keys=True) + "\n")
            return record

    def washout_status(self, reviewer_id: str, now: datetime | None = None) -> dict:
        """Days elapsed since this reviewer's last `primary` decision.

        Fails closed: with no primary decisions on record the washout is undefined, and
        an undefined washout is not a satisfied one.
        """
        now = now or datetime.now(timezone.utc)
        stamps = [
            datetime.fromisoformat(r["timestamp_utc"])
            for r in self.read_all("primary") if r.get("reviewer_id") == reviewer_id
        ]
        if not stamps:
            return {"reviewer_id": reviewer_id, "last_primary_utc": None,
                    "days_elapsed": 0.0, "required_days": WASHOUT_DAYS,
                    "satisfied": False,
                    "reason": "no primary decisions on record; washout is undefined"}
        last = max(stamps)
        elapsed = (now - last).total_seconds() / 86400.0
        return {
            "reviewer_id": reviewer_id,
            "last_primary_utc": last.isoformat(timespec="seconds"),
            "days_elapsed": elapsed,
            "required_days": WASHOUT_DAYS,
            "earliest_repeat_utc": (last + timedelta(days=WASHOUT_DAYS)).isoformat(
                timespec="seconds"),
            "satisfied": elapsed >= WASHOUT_DAYS,
            "reason": None if elapsed >= WASHOUT_DAYS else "washout not yet elapsed",
        }

    # -- agreement ---------------------------------------------------------------
    def paired_agreement(self, reviewer_a: str, round_a: str, reviewer_b: str,
                         round_b: str, item_pairs: list[tuple[str, str]]) -> dict:
        """Raw agreement and Cohen's kappa over paired items.

        `item_pairs` maps round-A item ids to round-B item ids -- the link lives in the
        private mapping, never in a reviewer-facing artifact. Used for the intra-rater
        comparison (same reviewer, primary vs repeat) and for the independent second
        reviewer. Neither comparison alters a stored label.
        """
        a_labels = {r["review_item_id"]: r["label"] for r in sorted(
            self.read_all(round_a), key=lambda r: r["timestamp_utc"])
            if r.get("reviewer_id") == reviewer_a}
        b_labels = {r["review_item_id"]: r["label"] for r in sorted(
            self.read_all(round_b), key=lambda r: r["timestamp_utc"])
            if r.get("reviewer_id") == reviewer_b}

        paired = [(a_labels[ia], b_labels[ib]) for ia, ib in item_pairs
                  if ia in a_labels and ib in b_labels]
        n = len(paired)
        if n == 0:
            return {"n_paired": 0, "raw_agreement": None, "cohens_kappa": None,
                    "note": "no paired decisions available"}
        agree = sum(1 for x, y in paired if x == y)
        p_o = agree / n
        p_e = sum(
            (sum(1 for x, _ in paired if x == lab) / n)
            * (sum(1 for _, y in paired if y == lab) / n)
            for lab in LABELS
        )
        kappa = None if p_e >= 1.0 else (p_o - p_e) / (1.0 - p_e)
        return {
            "n_paired": n,
            "n_agree": agree,
            "raw_agreement": round(p_o, 6),
            "expected_agreement": round(p_e, 6),
            "cohens_kappa": None if kappa is None else round(kappa, 6),
            "labels_a": {lab: sum(1 for x, _ in paired if x == lab) for lab in LABELS},
            "labels_b": {lab: sum(1 for _, y in paired if y == lab) for lab in LABELS},
        }

    # -- adjudication ------------------------------------------------------------
    def adjudicated_view(self, round_name: str) -> dict[str, dict]:
        """Latest non-superseded record per (item, reviewer), plus disagreement flags.

        Raw records are never modified. Disagreements stay visible: an item reviewed by two
        people who differ appears with `agreement=False` and both labels retained.
        """
        by_item: dict[str, dict[str, dict]] = {}
        for rec in sorted(self.read_all(round_name), key=lambda r: r["timestamp_utc"]):
            by_item.setdefault(rec["review_item_id"], {})[rec["reviewer_id"]] = rec
        out: dict[str, dict] = {}
        for item, per_reviewer in by_item.items():
            labels = {rid: r["label"] for rid, r in per_reviewer.items()}
            out[item] = {
                "labels_by_reviewer": labels,
                "n_reviewers": len(labels),
                "agreement": len(set(labels.values())) == 1,
                "records": list(per_reviewer.values()),
            }
        return out

    def progress(self, round_name: str, reviewer_id: str, n_total: int) -> dict:
        """Completion summary. Deliberately reveals nothing about threshold performance."""
        done = self.completed_items(round_name, reviewer_id)
        counts = {lab: 0 for lab in LABELS}
        for rec in self.read_all(round_name):
            if rec.get("reviewer_id") == reviewer_id:
                counts[rec["label"]] += 1
        return {
            "round": round_name, "reviewer_id": reviewer_id,
            "completed": len(done), "total": n_total,
            "remaining": max(0, n_total - len(done)),
            "label_counts": counts,
            "indeterminate_fraction": round(
                counts["indeterminate"] / max(1, len(done)), 4),
        }
