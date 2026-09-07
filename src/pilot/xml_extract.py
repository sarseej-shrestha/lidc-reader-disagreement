"""Read-only LIDC annotation-XML extraction, scoped to the association pilot.

This is deliberately NOT the production candidate-building parser. It extracts the
reader-mark table and nothing else: no candidate association, no clustering, no crop
extraction, no training data. Milestone 3 replaces it.

Scope rules implemented here are the ones frozen in docs/protocol.md 0.2.0-draft:
  - hash-pinned standalone corpus only; radiography (IdriReadMessage) excluded by root tag
  - duplicate submissions collapsed on annotation-payload hash; LIDC-IDRI-0101 resolved by
    the official TCIA erratum
  - nodule_ge_3mm = class A (populated characteristics AND multi-point contour)
                    or class B (the two documented erratum exceptions, by stable identity)
  - empty <characteristics/> is not equivalent to a populated one
  - inclusion=FALSE contours preserved and subtracted from mask volume
  - reading-session identity preserved; reader count is per scan, never assumed to be 4
  - the eight-session panel is excluded from the primary analysis
  - separate timepoints are separate series and are never associated together

Geometry note (important, and a known limitation):
    Mark centres are computed in millimetres from in-plane pixel indices scaled by
    PixelSpacing, with z taken from the XML's own imageZposition. The DICOM
    ImagePositionPatient origin is NOT applied, so coordinates are millimetre offsets in a
    per-series frame rather than absolute patient coordinates. Every distance used by the
    pilot is a WITHIN-SERIES difference, for which a constant origin cancels exactly.
    `verify_axial_geometry()` checks the assumption this relies on (axial, consistent
    orientation and spacing) rather than assuming it. The production parser must use the
    full index->world transform; see GEOMETRY_VERSION.
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

NS = "{http://www.nih.gov}"
IDRI_NS = "{http://www.nih.gov/idri}"

GEOMETRY_VERSION = "pilot-approx-v1"
EXTRACTION_VERSION = "pilot-xml-extract-v1"

#: SHA-256 of the pinned LIDC-XML-only.zip archive (docs/protocol.md 3.1).
CORPUS_SHA256 = "644557a3aa305602609c718b0cae33a93be762e8901a80bcd9df735b0ec6ab90"

#: Series whose reading-session panel is excluded from the primary analysis
#: (protocol 5.1: two concatenated four-reader panels, LIDC-IDRI-0566).
EXCLUDED_PANEL_SERIES_SUFFIX = ("137375498893536422914241295628",)

#: Series with a genuine payload difference resolved by official TCIA erratum
#: (2012-03-21, LIDC-IDRI-0101). The corrected resubmission is canonical.
ERRATUM_SUPERSEDED_SERIES_SUFFIX = "188094259402036602717327"
ERRATUM_CORRECTED_FILENAME_MARKER = "resubmitted-correction"

#: The two officially documented missing-characteristics exceptions (TCIA erratum
#: 2018-06-28). Keyed by (series-UID suffix, session index, noduleID) -- never by bare
#: filename, because the basenames 044.xml / 191.xml recur across directories for other
#: series and a filename key matches the wrong marks.
ERRATUM_GE3MM_EXCEPTIONS = frozenset({
    ("527162678142285870245028", 1, "Nodule 001"),   # LIDC-IDRI-0305
    ("525524522225658609808059", 2, "Nodule 002"),   # LIDC-IDRI-0447
})

CAT_GE3 = "nodule_ge_3mm"
CAT_LT3 = "nodule_lt_3mm"
CAT_NON = "non_nodule_ge_3mm"
CAT_AMBIG = "ambiguous_unresolved"

_UID_ATTR = re.compile(rb'\suid="[^"]*"')


def _q(tag: str) -> str:
    return NS + tag


@dataclass(frozen=True)
class Mark:
    """One explicit reader mark. `patient_id`/`series_uid` are private fields and must not
    reach any reviewer-facing artifact."""

    mark_id: str
    patient_id: str
    study_uid: str
    series_uid: str
    session_index: int
    category: str
    kind: str                 # "contour" | "point"
    x_mm: float
    y_mm: float
    z_mm: float
    radius_mm: float          # volume-equivalent sphere radius; 0.0 for point marks
    n_roi: int
    n_edge_points: int
    n_exclusion_roi: int      # inclusion=FALSE ROIs, preserved not dropped
    volume_mm3: float
    is_erratum_exception: bool = False
    ambiguity_reason: str | None = None


@dataclass
class ScanRecord:
    patient_id: str
    study_uid: str
    series_uid: str
    xml_path: str
    n_sessions: int
    marks: list[Mark] = field(default_factory=list)
    excluded_reason: str | None = None


def payload_hash(path: str) -> str:
    """Hash only the annotation payload: concatenated <readingSession> subtrees.

    Whole-document hashing is insufficient -- four series differ only in where
    <StudyInstanceUID> sits inside <ResponseHeader>, which a document hash misreports as a
    genuine content difference (protocol 3.4).
    """
    root = ET.parse(path).getroot()
    blobs = [ET.tostring(s, encoding="utf-8") for s in root.findall(_q("readingSession"))]
    return hashlib.sha256(b"".join(blobs)).hexdigest()


def document_hash(path: str) -> str:
    """SHA-256 of the file with the per-submission root uid attribute removed."""
    with open(path, "rb") as fh:
        return hashlib.sha256(_UID_ATTR.sub(b"", fh.read(), count=1)).hexdigest()


def index_corpus(corpus_root: str) -> tuple[dict[str, list[str]], Counter]:
    """Group XML paths by SeriesInstanceUid, excluding radiography by root tag.

    Returns (series_uid -> [paths], root-tag counts). Radiography documents use the
    IdriReadMessage root in a different namespace and are excluded by tag, never by
    filename.
    """
    by_series: dict[str, list[str]] = defaultdict(list)
    roots: Counter = Counter()
    for path in sorted(glob.glob(os.path.join(corpus_root, "**", "*.xml"), recursive=True)):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            roots["parse_error"] += 1
            continue
        roots[root.tag] += 1
        if root.tag != _q("LidcReadMessage"):
            continue
        uid = (root.findtext(f'{_q("ResponseHeader")}/{_q("SeriesInstanceUid")}') or "").strip()
        if uid:
            by_series[uid].append(path)
    return dict(by_series), roots


def select_source_file(series_uid: str, paths: list[str]) -> tuple[str | None, str]:
    """Deterministic source selection (protocol 3.4). Returns (path, rule) or (None, rule)."""
    if len(paths) == 1:
        return paths[0], "single"
    if series_uid.endswith(ERRATUM_SUPERSEDED_SERIES_SUFFIX):
        corrected = [p for p in paths if ERRATUM_CORRECTED_FILENAME_MARKER in os.path.basename(p)]
        if len(corrected) == 1:
            return corrected[0], "tcia_erratum_2012_03_21"
    hashes = {p: payload_hash(p) for p in paths}
    if len(set(hashes.values())) == 1:
        return sorted(paths)[0], f"payload_identical_x{len(paths)}"
    return None, "payload_differs_no_erratum__EXCLUDE"


def _shoelace(points: list[tuple[float, float]]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def is_erratum_exception(series_uid: str, session_index: int, nodule_id: str | None) -> bool:
    nid = (nodule_id or "").strip()
    return any(
        series_uid.endswith(suffix) and session_index == sess and nid == name
        for suffix, sess, name in ERRATUM_GE3MM_EXCEPTIONS
    )


def extract_scan(
    xml_path: str,
    patient_id: str,
    pixel_spacing_mm: float,
    slice_spacing_mm: float,
) -> ScanRecord:
    """Extract every explicit mark from one selected XML file.

    `pixel_spacing_mm` and `slice_spacing_mm` come from the DICOM series, supplied by the
    caller so this module never touches pixel data.
    """
    root = ET.parse(xml_path).getroot()
    header = root.find(_q("ResponseHeader"))
    series_uid = (header.findtext(_q("SeriesInstanceUid")) or "").strip()
    study_uid = (header.findtext(_q("StudyInstanceUID")) or "").strip()
    sessions = root.findall(_q("readingSession"))

    rec = ScanRecord(
        patient_id=patient_id,
        study_uid=study_uid,
        series_uid=series_uid,
        xml_path=xml_path,
        n_sessions=len(sessions),
    )
    if any(series_uid.endswith(s) for s in EXCLUDED_PANEL_SERIES_SUFFIX):
        # Marks are still extracted so the corpus-scope reconciliation gate can see them;
        # the flag is what removes the series from the primary analysis downstream.
        rec.excluded_reason = "excluded_reader_panel__concatenated_four_reader_panels"

    for session_index, session in enumerate(sessions):
        for node in session.findall(_q("unblindedReadNodule")):
            mark = _extract_nodule(
                node, series_uid, study_uid, patient_id, session_index,
                pixel_spacing_mm, slice_spacing_mm,
            )
            if mark is not None:
                rec.marks.append(mark)
        for node in session.findall(_q("nonNodule")):
            mark = _extract_non_nodule(
                node, series_uid, study_uid, patient_id, session_index, pixel_spacing_mm,
            )
            if mark is not None:
                rec.marks.append(mark)
    return rec


def _extract_nodule(node, series_uid, study_uid, patient_id, session_index,
                    ps_mm, sp_mm) -> Mark | None:
    nodule_id = (node.findtext(_q("noduleID")) or "").strip()
    characteristics = node.find(_q("characteristics"))
    # An empty <characteristics/> is NOT a populated one. `is not None` misclassifies the
    # 18 self-closing occurrences in the corpus.
    populated = characteristics is not None and len(list(characteristics)) > 0

    rois = node.findall(_q("roi"))
    pts: list[tuple[float, float, float]] = []
    volume = 0.0
    n_exclusion = 0
    for roi in rois:
        z_mm = float(roi.findtext(_q("imageZposition")))
        included = (roi.findtext(_q("inclusion")) or "TRUE").strip().upper() == "TRUE"
        if not included:
            n_exclusion += 1
        plane = [
            (float(em.findtext(_q("xCoord"))) * ps_mm,
             float(em.findtext(_q("yCoord"))) * ps_mm)
            for em in roi.findall(_q("edgeMap"))
        ]
        pts.extend((x, y, z_mm) for x, y in plane)
        if len(plane) >= 3:
            slab = _shoelace(plane) * sp_mm
            volume += slab if included else -slab   # exclusion contours subtract
    if not pts:
        return None

    n_edge = len(pts)
    contour = n_edge > 1
    exception = is_erratum_exception(series_uid, session_index, nodule_id)

    if populated and contour:
        category, ambiguity = CAT_GE3, None
    elif (not populated) and contour and exception:
        category, ambiguity = CAT_GE3, None          # class B, on erratum authority
    elif populated and not contour:
        category = CAT_AMBIG
        ambiguity = "populated_characteristics_single_point"
    elif (not populated) and contour:
        category = CAT_AMBIG
        ambiguity = "no_characteristics_multipoint_contour_not_in_erratum"
    else:
        category, ambiguity = CAT_LT3, None

    cx = sum(p[0] for p in pts) / n_edge
    cy = sum(p[1] for p in pts) / n_edge
    cz = sum(p[2] for p in pts) / n_edge
    if contour and volume > 0.0:
        radius = (3.0 * volume / (4.0 * 3.141592653589793)) ** (1.0 / 3.0)
    else:
        radius = 0.0

    return Mark(
        mark_id=f"{series_uid}|nod|{session_index}|{nodule_id}",
        patient_id=patient_id, study_uid=study_uid, series_uid=series_uid,
        session_index=session_index, category=category,
        kind="contour" if contour else "point",
        x_mm=cx, y_mm=cy, z_mm=cz, radius_mm=radius,
        n_roi=len(rois), n_edge_points=n_edge, n_exclusion_roi=n_exclusion,
        volume_mm3=max(volume, 0.0),
        is_erratum_exception=exception, ambiguity_reason=ambiguity,
    )


def _extract_non_nodule(node, series_uid, study_uid, patient_id, session_index,
                        ps_mm) -> Mark | None:
    locus = node.find(_q("locus"))
    if locus is None:
        return None
    non_nodule_id = (node.findtext(_q("nonNoduleID")) or "").strip()
    return Mark(
        mark_id=f"{series_uid}|non|{session_index}|{non_nodule_id}",
        patient_id=patient_id, study_uid=study_uid, series_uid=series_uid,
        session_index=session_index, category=CAT_NON, kind="point",
        x_mm=float(locus.findtext(_q("xCoord"))) * ps_mm,
        y_mm=float(locus.findtext(_q("yCoord"))) * ps_mm,
        z_mm=float(node.findtext(_q("imageZposition"))),
        radius_mm=0.0, n_roi=0, n_edge_points=1, n_exclusion_roi=0, volume_mm3=0.0,
    )


def summarise(records: Iterable[ScanRecord], scope: str = "corpus") -> dict:
    """Aggregate mark counts.

    Two scopes, and the distinction matters:

    ``corpus``
        Every parsed CT series, *including* the excluded reader panel. This is the scope of
        the frozen reconciliation gate, because the gate's job is to prove the parser reads
        the XML correctly -- which is independent of any later analysis-scope decision.

    ``primary``
        The primary-analysis scope: the excluded reader panel is dropped. This is what feeds
        the pair pool.
    """
    if scope not in ("corpus", "primary"):
        raise ValueError("scope must be 'corpus' or 'primary'")
    counts = Counter()
    sessions_hist = Counter()
    for rec in records:
        if rec.excluded_reason:
            counts["series_excluded"] += 1
            if scope == "primary":
                continue
        else:
            counts["series_used"] += 1
        sessions_hist[rec.n_sessions] += 1
        for mark in rec.marks:
            if mark.category == CAT_GE3:
                counts["ge3_class_b" if mark.is_erratum_exception else "ge3_class_a"] += 1
            elif mark.category == CAT_LT3:
                counts["lt3"] += 1
            elif mark.category == CAT_NON:
                counts["non_nodule"] += 1
            else:
                counts["ambiguous"] += 1
            counts["exclusion_roi_total"] += mark.n_exclusion_roi
    counts["ge3_total"] = counts["ge3_class_a"] + counts["ge3_class_b"]
    counts["marks_total"] = (
        counts["ge3_total"] + counts["lt3"] + counts["non_nodule"] + counts["ambiguous"]
    )
    counts["series_in_scope"] = sum(sessions_hist.values())
    return {"scope": scope, "counts": dict(counts),
            "sessions_per_series": dict(sorted(sessions_hist.items()))}


#: Primary-analysis scope: corpus counts minus the excluded panel's 84 marks
#: (4 ge3 + 16 lt3 + 64 non-nodule). Recorded so the difference is auditable rather than
#: surprising, and asserted as a cross-check.
EXPECTED_PRIMARY = {
    "series_in_scope": 1017,
    "ge3_class_a": 6855,
    "ge3_class_b": 2,
    "ge3_total": 6857,
    "lt3": 13217,
    "non_nodule": 21599,
    "ambiguous": 2,
    "marks_total": 41675,
}

EXCLUDED_PANEL_MARK_COUNTS = {"ge3": 4, "lt3": 16, "non_nodule": 64, "total": 84}


class ReconciliationError(RuntimeError):
    """Raised when aggregate counts differ from the frozen expectation."""


#: Frozen expectations (protocol label_schema 3, verified 2026-08-31).
#:
#: SCOPE: these are CORPUS-scope counts, over all 1,018 CT series *including* the excluded
#: eight-session reader panel (LIDC-IDRI-0566). That is how they were originally computed.
#: The primary-analysis scope drops that panel's 84 marks -- see EXPECTED_PRIMARY. Applying
#: the gate at corpus scope keeps it a pure parser check, independent of analysis-scope
#: decisions, and it is the reason the two figures differ.
EXPECTED = {
    "xml_files": 1319,
    "ct_series": 1018,
    "ge3_class_a": 6859,
    "ge3_class_b": 2,
    "ge3_total": 6861,
    "lt3": 13233,
    "non_nodule": 21663,
    "ambiguous": 2,
    "marks_total": 41759,
}


def assert_reconciled(summary: dict, xml_files: int, ct_series: int,
                      expected: dict | None = None) -> None:
    """Fail closed on any deviation. A mismatch is never repaired by weakening a rule."""
    expected = EXPECTED if expected is None else expected
    observed = dict(summary["counts"])
    observed["xml_files"] = xml_files
    observed["ct_series"] = ct_series
    bad = {k: (v, observed.get(k)) for k, v in expected.items() if observed.get(k) != v}
    if bad:
        lines = [f"  {k}: expected {exp}, observed {obs}" for k, (exp, obs) in sorted(bad.items())]
        raise ReconciliationError(
            "aggregate reconciliation FAILED -- refusing to generate a manifest:\n"
            + "\n".join(lines)
        )
