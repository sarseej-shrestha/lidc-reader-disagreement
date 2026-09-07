"""Pilot-scope tests. Synthetic fixtures only -- no LIDC XML or patient imagery."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.pilot import manifest as M
from src.pilot import matching as MT
from src.pilot import pool as POOL
from src.pilot import review_app as APP
from src.pilot import review_store as RS
from src.pilot import split_validation as SV
from src.pilot import xml_extract as X
from tests.pilot import synthetic as S

SERIES_A = "1.3.6.1.4.1.99999.1.111111111111111111111111"
SERIES_B = "1.3.6.1.4.1.99999.1.222222222222222222222222"


def _mark(mark_id="m", series=SERIES_A, session=0, kind="point", x=0.0, y=0.0, z=0.0,
          radius=0.0, category=X.CAT_NON, patient="P1"):
    return X.Mark(mark_id=mark_id, patient_id=patient, study_uid="S", series_uid=series,
                  session_index=session, category=category, kind=kind,
                  x_mm=x, y_mm=y, z_mm=z, radius_mm=radius, n_roi=1, n_edge_points=1,
                  n_exclusion_roi=0, volume_mm3=0.0)


# ---------------------------------------------------------------- extraction ----------
def test_radiography_excluded_by_root_tag():
    with tempfile.TemporaryDirectory() as tmp:
        S.write(tmp, "ct.xml", S.lidc_xml(SERIES_A, [S.session(S.non_nodule("n1", 5, 10, 10))]))
        S.write(tmp, "xray.xml", S.idri_xml("1.2.3.4"))
        by_series, roots = X.index_corpus(tmp)
        assert list(by_series) == [SERIES_A]
        assert roots["{http://www.nih.gov/idri}IdriReadMessage"] == 1


# ------------------------------------------------- 5.1 #1 namespace and root tags ----
_NIH = "http://www.nih.gov"


def _doc(root_local: str, ns: str | None, uid: str) -> str:
    """A minimal LIDC-shaped document with a controllable root tag and namespace."""
    xmlns = f' xmlns="{ns}"' if ns else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<{root_local}{xmlns}>'
            f"<ResponseHeader><SeriesInstanceUid>{uid}</SeriesInstanceUid></ResponseHeader>"
            f"</{root_local}>")


def test_index_corpus_accepts_the_nih_lidc_namespace():
    with tempfile.TemporaryDirectory() as tmp:
        S.write(tmp, "a.xml", _doc("LidcReadMessage", _NIH, "1.1.1"))
        by_series, roots = X.index_corpus(tmp)
        assert list(by_series) == ["1.1.1"]
        assert roots["{http://www.nih.gov}LidcReadMessage"] == 1


def test_index_corpus_rejects_correct_local_name_in_the_wrong_namespace():
    """`LidcReadMessage` under the IDRI namespace is NOT a CT read."""
    with tempfile.TemporaryDirectory() as tmp:
        S.write(tmp, "a.xml", _doc("LidcReadMessage", "http://www.nih.gov/idri", "2.2.2"))
        by_series, roots = X.index_corpus(tmp)
        assert by_series == {}, "namespace must be part of the comparison"
        assert roots["{http://www.nih.gov/idri}LidcReadMessage"] == 1


def test_index_corpus_rejects_correct_local_name_with_no_namespace():
    with tempfile.TemporaryDirectory() as tmp:
        S.write(tmp, "a.xml", _doc("LidcReadMessage", None, "3.3.3"))
        by_series, roots = X.index_corpus(tmp)
        assert by_series == {}, "an unqualified root must not be accepted"
        assert roots["LidcReadMessage"] == 1


def test_index_corpus_counts_malformed_xml_as_parse_error_and_excludes_it():
    with tempfile.TemporaryDirectory() as tmp:
        S.write(tmp, "broken.xml", "<LidcReadMessage><unclosed>")
        S.write(tmp, "ok.xml", _doc("LidcReadMessage", _NIH, "4.4.4"))
        by_series, roots = X.index_corpus(tmp)
        assert roots["parse_error"] == 1
        assert list(by_series) == ["4.4.4"], "a broken file must not enter the result"


def test_rejected_documents_never_enter_the_indexed_series_result():
    """Every rejection path at once: the accepted set is exactly the valid CT documents."""
    with tempfile.TemporaryDirectory() as tmp:
        S.write(tmp, "ct.xml", _doc("LidcReadMessage", _NIH, "5.5.5"))
        S.write(tmp, "idri.xml", S.idri_xml("6.6.6"))
        S.write(tmp, "wrongns.xml", _doc("LidcReadMessage", "http://www.nih.gov/idri", "7.7.7"))
        S.write(tmp, "nons.xml", _doc("LidcReadMessage", None, "8.8.8"))
        S.write(tmp, "bad.xml", "<not xml")
        by_series, roots = X.index_corpus(tmp)
        assert set(by_series) == {"5.5.5"}
        for leaked in ("6.6.6", "7.7.7", "8.8.8"):
            assert leaked not in by_series
        assert sum(roots.values()) == 5, "every document is accounted for in the root census"


def test_reconciliation_gate_detects_an_aggregate_shortfall():
    """If rejected documents silently reduced the corpus, the frozen gate must fail."""
    short = {"counts": dict(X.EXPECTED), "sessions_per_series": {}}
    short["counts"]["marks_total"] -= 1
    with pytest.raises(X.ReconciliationError):
        X.assert_reconciled(short, xml_files=X.EXPECTED["xml_files"],
                            ct_series=X.EXPECTED["ct_series"])
    with pytest.raises(X.ReconciliationError):
        X.assert_reconciled({"counts": dict(X.EXPECTED), "sessions_per_series": {}},
                            xml_files=X.EXPECTED["xml_files"],
                            ct_series=X.EXPECTED["ct_series"] - 1)


# ------------------------------------------------- 5.1 #2 tag, never filename --------
def test_ct_document_with_a_radiography_like_filename_is_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("IdriReadMessage.xml", "idri_radiography_xray.xml", "xray.xml"):
            sub = os.path.join(tmp, name.replace(".xml", ""))
            os.makedirs(sub, exist_ok=True)
            S.write(sub, name, _doc("LidcReadMessage", _NIH, "9." + str(len(name))))
        by_series, _ = X.index_corpus(tmp)
        assert len(by_series) == 3, "filename must not exclude a genuine CT document"


def test_radiography_document_with_a_ct_like_filename_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("LidcReadMessage.xml", "ct_scan.xml", "lidc_nodule_read.xml"):
            sub = os.path.join(tmp, name.replace(".xml", ""))
            os.makedirs(sub, exist_ok=True)
            S.write(sub, name, S.idri_xml("8." + str(len(name))))
        by_series, roots = X.index_corpus(tmp)
        assert by_series == {}, "filename must not admit a radiography document"
        assert roots["{http://www.nih.gov/idri}IdriReadMessage"] == 3


def test_filename_and_extension_stem_never_change_the_ct_decision():
    """Identical bytes under many filenames must produce an identical decision."""
    ct = _doc("LidcReadMessage", _NIH, "7.7.7")
    idri = S.idri_xml("7.7.7")
    for body, expect_accept in ((ct, True), (idri, False)):
        results = []
        for i, name in enumerate(("a.xml", "IdriReadMessage.xml", "LidcReadMessage.xml",
                                  "ZZZ.xml", "1.3.6.1.4.1.14519.xml")):
            with tempfile.TemporaryDirectory() as tmp:
                S.write(tmp, name, body)
                results.append(bool(X.index_corpus(tmp)[0]))
        assert len(set(results)) == 1, "decision varied with filename"
        assert results[0] is expect_accept


def test_empty_characteristics_is_not_populated():
    """An empty <characteristics/> must not be treated as a populated one."""
    with tempfile.TemporaryDirectory() as tmp:
        rois = S.contour_roi(1, 20, 20) + S.contour_roi(2, 20, 20)
        path = S.write(tmp, "a.xml", S.lidc_xml(SERIES_A, [
            S.session(S.nodule("n-pop", rois, S.CHARACTERISTICS)),
            S.session(S.nodule("n-empty", rois, S.EMPTY_CHARACTERISTICS)),
        ]))
        rec = X.extract_scan(path, "P1", 0.7, 1.0)
        cats = {m.mark_id.split("|")[-1]: m.category for m in rec.marks}
        assert cats["n-pop"] == X.CAT_GE3
        # empty characteristics + contour and NOT an erratum -> ambiguous, never ge3
        assert cats["n-empty"] == X.CAT_AMBIG


# ------------------------------------------- 5.1 #3 characteristics semantics --------
# label_schema.md 3 defines the distinction as POPULATED vs NOT-POPULATED, and treats
# "empty" and "absent" as deliberately equivalent. These tests pin that equivalence so a
# future refactor cannot quietly start treating an empty element as populated.
_CONTOUR = None      # built per-test


def _nodule_doc(characteristics: str, uid: str, contour: bool = True) -> str:
    rois = (S.contour_roi(1, 20, 20) + S.contour_roi(2, 20, 20)) if contour \
        else S.point_roi(1, 20, 20)
    return S.lidc_xml(uid, [S.session(S.nodule("n1", rois, characteristics))])


_CHAR_STATES = {
    "populated":      S.CHARACTERISTICS,
    "empty":          "<characteristics/>",
    "absent":         "",
    "whitespace":     "<characteristics>   </characteristics>",
    "comment":        "<characteristics><!-- no ratings recorded --></characteristics>",
    "empty_paired":   "<characteristics></characteristics>",
}


def _category_for(state: str, contour: bool = True) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = S.write(tmp, "a.xml", _nodule_doc(_CHAR_STATES[state], f"1.2.{state}", contour))
        return X.extract_scan(path, "P1", 1.0, 1.0).marks[0].category


def test_populated_characteristics_plus_contour_yields_ge3():
    assert _category_for("populated") == X.CAT_GE3


def test_empty_absent_whitespace_and_comment_characteristics_are_all_not_populated():
    """The four not-populated states must be indistinguishable in the result."""
    got = {st: _category_for(st) for st in
           ("empty", "absent", "whitespace", "comment", "empty_paired")}
    assert set(got.values()) == {X.CAT_AMBIG}, got
    assert got["empty"] == got["absent"], \
        "label_schema treats empty and absent as equivalent; they must not diverge"


def test_not_populated_states_share_one_ambiguity_reason():
    with tempfile.TemporaryDirectory() as tmp:
        reasons = set()
        for st in ("empty", "absent", "whitespace", "comment"):
            path = S.write(tmp, f"{st}.xml", _nodule_doc(_CHAR_STATES[st], f"3.3.{st}"))
            reasons.add(X.extract_scan(path, "P1", 1.0, 1.0).marks[0].ambiguity_reason)
        assert reasons == {"no_characteristics_multipoint_contour_not_in_erratum"}


def test_a_single_point_mark_is_lt3_regardless_of_empty_or_absent_characteristics():
    """Without a multi-point contour the ge3 rule cannot fire; not-populated + point is <3 mm."""
    for st in ("empty", "absent", "whitespace", "comment"):
        assert _category_for(st, contour=False) == X.CAT_LT3, st


def test_populated_characteristics_on_a_single_point_is_ambiguous_not_ge3():
    """The two structurally ambiguous corpus marks (label_schema 3.3)."""
    assert _category_for("populated", contour=False) == X.CAT_AMBIG
    with tempfile.TemporaryDirectory() as tmp:
        path = S.write(tmp, "a.xml", _nodule_doc(S.CHARACTERISTICS, "4.4.4", contour=False))
        m = X.extract_scan(path, "P1", 1.0, 1.0).marks[0]
        assert m.ambiguity_reason == "populated_characteristics_single_point"


def test_class_b_erratum_promotes_only_the_exact_named_marks():
    """Class B must not generalise to every empty <characteristics/> (label_schema 3)."""
    uid = "1.3.6.1.4.1.9.527162678142285870245028"          # the erratum series
    with tempfile.TemporaryDirectory() as tmp:
        rois = S.contour_roi(1, 20, 20) + S.contour_roi(2, 20, 20)
        # session 1 / "Nodule 001" is the named mark; the others are not
        path = S.write(tmp, "a.xml", S.lidc_xml(uid, [
            S.session(S.nodule("Nodule 001", rois, S.EMPTY_CHARACTERISTICS)),   # session 0
            S.session(S.nodule("Nodule 001", rois, S.EMPTY_CHARACTERISTICS)),   # session 1 -> B
            S.session(S.nodule("Nodule 002", rois, S.EMPTY_CHARACTERISTICS)),   # session 2
        ]))
        marks = {(m.session_index, m.mark_id.split("|")[-1]): m
                 for m in X.extract_scan(path, "P1", 1.0, 1.0).marks}
        promoted = [k for k, m in marks.items() if m.is_erratum_exception]
        assert promoted == [(1, "Nodule 001")], promoted
        assert marks[(1, "Nodule 001")].category == X.CAT_GE3
        assert marks[(0, "Nodule 001")].category == X.CAT_AMBIG
        assert marks[(2, "Nodule 002")].category == X.CAT_AMBIG


def test_reconciliation_encodes_the_empty_characteristics_accounting():
    """The frozen corpus gate is what pins the 18 empty occurrences: class A reconciles to
    pylidc's 6,859 and only 2 documented exceptions are added. Aggregate check only."""
    assert X.EXPECTED["ge3_class_a"] == 6859
    assert X.EXPECTED["ge3_class_b"] == 2
    assert X.EXPECTED["ge3_total"] == X.EXPECTED["ge3_class_a"] + X.EXPECTED["ge3_class_b"]
    assert X.EXPECTED["ambiguous"] == 2
    assert len(X.ERRATUM_GE3MM_EXCEPTIONS) == 2
    drifted = {"counts": dict(X.EXPECTED), "sessions_per_series": {}}
    drifted["counts"]["ge3_class_b"] = 20          # as if every empty element were promoted
    with pytest.raises(X.ReconciliationError):
        X.assert_reconciled(drifted, xml_files=X.EXPECTED["xml_files"],
                            ct_series=X.EXPECTED["ct_series"])


def test_exclusion_contours_preserved_and_subtracted():
    with tempfile.TemporaryDirectory() as tmp:
        rois = (S.contour_roi(1, 20, 20, r=6) + S.contour_roi(2, 20, 20, r=6)
                + S.contour_roi(2, 20, 20, r=2, inclusion="FALSE"))
        path = S.write(tmp, "a.xml", S.lidc_xml(SERIES_A, [S.session(S.nodule("n1", rois))]))
        rec = X.extract_scan(path, "P1", 1.0, 1.0)
        mark = rec.marks[0]
        assert mark.n_exclusion_roi == 1, "inclusion=FALSE ROI must be counted, not dropped"
        solid = (S.contour_roi(1, 20, 20, r=6) + S.contour_roi(2, 20, 20, r=6))
        path2 = S.write(tmp, "b.xml", S.lidc_xml(SERIES_B, [S.session(S.nodule("n1", solid))]))
        ref = X.extract_scan(path2, "P1", 1.0, 1.0).marks[0]
        assert mark.volume_mm3 < ref.volume_mm3, "exclusion contour must subtract volume"


def test_erratum_exception_key_is_stable_and_specific():
    """The exception is keyed by series+session+noduleID, never by filename."""
    assert X.is_erratum_exception("x." + "527162678142285870245028", 1, "Nodule 001")
    assert not X.is_erratum_exception("x." + "527162678142285870245028", 2, "Nodule 001")
    assert not X.is_erratum_exception("x." + "527162678142285870245028", 1, "Nodule 002")
    assert not X.is_erratum_exception("x.999", 1, "Nodule 001")
    assert len(X.ERRATUM_GE3MM_EXCEPTIONS) == 2


def test_erratum_exception_promotes_to_ge3():
    uid = "1.3.6.1.4.1.9.527162678142285870245028"
    with tempfile.TemporaryDirectory() as tmp:
        rois = S.contour_roi(1, 20, 20) + S.contour_roi(2, 20, 20)
        path = S.write(tmp, "a.xml", S.lidc_xml(uid, [
            S.session(S.non_nodule("nn", 9, 5, 5)),
            S.session(S.nodule("Nodule 001", rois, S.EMPTY_CHARACTERISTICS)),
        ]))
        rec = X.extract_scan(path, "P1", 1.0, 1.0)
        promoted = [m for m in rec.marks if m.is_erratum_exception]
        assert len(promoted) == 1 and promoted[0].category == X.CAT_GE3


def test_three_session_denominator_not_assumed_four():
    with tempfile.TemporaryDirectory() as tmp:
        path = S.write(tmp, "a.xml", S.lidc_xml(SERIES_A, [
            S.session(S.non_nodule("n1", 1, 10, 10)),
            S.session(S.non_nodule("n2", 1, 11, 10)),
            S.session(S.non_nodule("n3", 1, 12, 10)),
        ]))
        rec = X.extract_scan(path, "P1", 1.0, 1.0)
        assert rec.n_sessions == 3
        assert {m.session_index for m in rec.marks} == {0, 1, 2}


def test_eight_session_panel_flagged_excluded_but_marks_still_parsed():
    uid = "1.3.6.1.4.1.9." + X.EXCLUDED_PANEL_SERIES_SUFFIX[0]
    with tempfile.TemporaryDirectory() as tmp:
        path = S.write(tmp, "a.xml", S.lidc_xml(
            uid, [S.session(S.non_nodule(f"n{i}", 1, 10 + i, 10)) for i in range(8)]))
        rec = X.extract_scan(path, "P1", 1.0, 1.0)
        assert rec.excluded_reason and "reader_panel" in rec.excluded_reason
        # corpus-scope gate must still see the marks; the flag is the analysis-scope decision
        assert len(rec.marks) == 8
        assert X.summarise([rec], scope="primary")["counts"].get("non_nodule", 0) == 0
        assert X.summarise([rec], scope="corpus")["counts"]["non_nodule"] == 8


def test_physical_coordinates_scale_with_pixel_spacing():
    with tempfile.TemporaryDirectory() as tmp:
        path = S.write(tmp, "a.xml", S.lidc_xml(
            SERIES_A, [S.session(S.non_nodule("n1", 7.5, 100, 40))]))
        m1 = X.extract_scan(path, "P1", 0.5, 1.0).marks[0]
        m2 = X.extract_scan(path, "P1", 1.0, 1.0).marks[0]
        assert m1.x_mm == pytest.approx(50.0) and m2.x_mm == pytest.approx(100.0)
        assert m1.z_mm == pytest.approx(7.5), "z comes from imageZposition in mm"


def test_reconciliation_fails_closed():
    with pytest.raises(X.ReconciliationError):
        X.assert_reconciled({"counts": {"ge3_class_a": 1}}, xml_files=1, ct_series=1)


# ---------------------------------------------------------------- pool ---------------
def test_pool_predicate_boundary_equality_is_eligible():
    a = _mark("a", session=0)
    b = _mark("b", session=1, x=POOL.POOL_FLOOR_MM)     # exactly 12.0 mm
    assert POOL.distance_mm(a, b) == pytest.approx(12.0)
    assert POOL.is_eligible(a, b), "<= is inclusive at the boundary"
    c = _mark("c", session=1, x=POOL.POOL_FLOOR_MM + 1e-6)
    assert not POOL.is_eligible(a, c)


def test_pool_radius_expanded_eligibility():
    """Large contours raise the bound; distance still governs."""
    a = _mark("a", session=0, kind="contour", radius=9.0)
    b = _mark("b", session=1, kind="contour", radius=9.0, x=17.0)
    assert POOL.pool_threshold_mm(a, b) == pytest.approx(18.0)
    assert POOL.is_eligible(a, b) and POOL.distance_mm(a, b) > POOL.POOL_FLOOR_MM
    far = _mark("f", session=1, kind="contour", radius=9.0, x=25.0)
    assert not POOL.is_eligible(a, far), \
        "a large contour does NOT admit any distance -- the predicate stays conjunctive"


def test_radius_expanded_only_predicate_requires_both_conditions():
    """r_i + r_j > 12 AND 12 < d <= r_i + r_j. Neither alone is sufficient."""
    assert POOL.is_radius_expanded_only(17.0, 9.0, 9.0)          # both hold
    assert not POOL.is_radius_expanded_only(11.0, 9.0, 9.0), \
        "d <= 12 mm: the 12 mm floor already admitted it, not the size term"
    assert not POOL.is_radius_expanded_only(13.0, 3.0, 3.0), \
        "r_i + r_j <= 12 mm: the size term never raised the bound"
    assert not POOL.is_radius_expanded_only(19.0, 9.0, 9.0), \
        "d > r_i + r_j: not eligible at all"
    assert not POOL.is_radius_expanded_only(12.0, 9.0, 9.0), "boundary is exclusive at 12"
    assert POOL.is_radius_expanded_only(18.0, 9.0, 9.0), "boundary inclusive at r_i + r_j"


def test_near_miss_band_is_exact_and_inclusive():
    assert POOL.is_near_miss(2.0) and POOL.is_near_miss(10.0), "both ends inclusive"
    assert not POOL.is_near_miss(1.999) and not POOL.is_near_miss(10.001)
    assert POOL.enrichment_band(5.0) == "near_miss"
    assert POOL.enrichment_band(0.5) == "other" and POOL.enrichment_band(11.0) == "other"


def test_grid_discrimination_is_geometry_only():
    """A pair every setting merges, and one the settings disagree about."""
    def _pair(d, r=0.0):
        return POOL.Pair(pair_id="x", patient_id="P", study_uid="S", series_uid="U",
                         mark_id_a="a", mark_id_b="b", session_index_a=0, session_index_b=1,
                         geometry_type="point-point", d_mm=d, r_a_mm=r, r_b_mm=r,
                         pool_threshold_mm=12.0, radius_expanded_only=False,
                         category_a=X.CAT_NON, category_b=X.CAT_NON,
                         max_contour_size_mm=0.0, slice_thickness_mm=1.0)
    assert len(POOL.grid_merge_predictions(_pair(1.0))) == 15
    assert not POOL.is_grid_discriminating(_pair(0.5)), "every setting merges"
    assert not POOL.is_grid_discriminating(_pair(11.0)), "no setting merges"
    assert POOL.is_grid_discriminating(_pair(4.5)), "tau_floor 4 splits, 5 merges"


def test_pool_same_session_and_cross_series_never_paired():
    a = _mark("a", session=0)
    assert not POOL.is_eligible(a, _mark("b", session=0, x=1.0)), "same reader"
    assert not POOL.is_eligible(a, _mark("b", series=SERIES_B, session=1, x=1.0)), \
        "different series / timepoint"


def test_no_cross_timepoint_pairing_in_build_pool():
    """Two timepoints of one patient must not produce cross-series pairs."""
    marks_a = [_mark("a0", SERIES_A, 0), _mark("a1", SERIES_A, 1, x=1.0)]
    marks_b = [_mark("b0", SERIES_B, 0), _mark("b1", SERIES_B, 1, x=1.0)]
    pool = POOL.build_pool({
        SERIES_A: ("P1", "ST1", marks_a, 1.0),
        SERIES_B: ("P1", "ST2", marks_b, 1.0),
    })
    assert len(pool) == 2
    assert all(p.series_uid in (SERIES_A, SERIES_B) for p in pool)
    for p in pool:
        assert p.mark_id_a[0] == p.mark_id_b[0], "both marks from the same series"


def test_pool_is_category_blind():
    """Changing only the category must not change eligibility or the pair id."""
    a = _mark("a", session=0, category=X.CAT_NON)
    b = _mark("b", session=1, x=3.0, category=X.CAT_NON)
    a2 = _mark("a", session=0, category=X.CAT_GE3)
    b2 = _mark("b", session=1, x=3.0, category=X.CAT_LT3)
    assert POOL.is_eligible(a, b) == POOL.is_eligible(a2, b2)
    assert POOL.pair_id("a", "b") == POOL.pair_id("b", "a"), "order-independent"


def test_ambiguous_category_does_not_alter_pool_eligibility():
    """Ratified 0.2.1-draft: association is category-agnostic, so an
    `ambiguous_unresolved` mark stays eligible for pairing even though it is excluded from
    the downstream benchmark label space. Excluding it here would make a physical question
    depend on a category decision.
    """
    every = (X.CAT_GE3, X.CAT_LT3, X.CAT_NON, X.CAT_AMBIG)
    baseline = None
    for cat_a in every:
        for cat_b in every:
            a = _mark("a", session=0, category=cat_a)
            b = _mark("b", session=1, x=3.0, category=cat_b)
            pool = POOL.build_pool({SERIES_A: ("P1", "ST", [a, b], 1.0)})
            fingerprint = [(p.pair_id, p.geometry_type, p.d_mm, POOL.cell_of(p))
                           for p in pool]
            if baseline is None:
                baseline = fingerprint
            assert fingerprint == baseline, \
                f"category pair ({cat_a}, {cat_b}) changed pool membership or stratum"
    assert len(baseline) == 1
    # and the boundary case: an ambiguous mark at the exact predicate boundary
    amb = _mark("a", session=0, category=X.CAT_AMBIG)
    far = _mark("b", session=1, x=POOL.POOL_FLOOR_MM, category=X.CAT_AMBIG)
    assert POOL.is_eligible(amb, far)


def test_pool_reconciliation_fails_closed():
    with pytest.raises(POOL.PoolReconciliationError):
        POOL.assert_pool_reconciled({"total": 1, "radius_expanded_only": 0,
                                     "patients_with_pairs": 0, "by_pair_type": {}})


# ---------------------------------------------------------------- matching -----------
def _availability(counts: dict[str, int] | None = None) -> dict[str, set[str]]:
    """One patient per unit of each cell's quota, each eligible for exactly that cell."""
    counts = counts or dict(MT.CELL_QUOTAS)
    avail: dict[str, set[str]] = {}
    i = 0
    for cell in sorted(counts):
        for _ in range(counts[cell]):
            avail[f"P{i:04d}"] = {cell}
            i += 1
    return avail


def test_joint_quotas_sum_to_the_pair_type_and_near_miss_totals():
    assert MT.TOTAL_QUOTA == 600
    assert MT.PAIR_TYPE_QUOTAS == {"point-point": 240, "point-contour": 180,
                                   "contour-contour": 180}
    near = {k: v for k, v in MT.CELL_QUOTAS.items() if k.endswith("|near_miss")}
    assert sum(near.values()) == 300
    assert near == {"point-point|near_miss": 120, "point-contour|near_miss": 90,
                    "contour-contour|near_miss": 90}
    for gt, total in MT.PAIR_TYPE_QUOTAS.items():
        assert sum(v for k, v in MT.CELL_QUOTAS.items() if k.startswith(gt + "|")) == total


def test_joint_maxflow_feasible_exact_quotas():
    res = MT.assign_patients(_availability(), seed=1)
    assert res.feasible and res.achieved_flow == 600
    assert res.filled == MT.CELL_QUOTAS
    assert len(res.assignment) == len(set(res.assignment)) == 600
    proof = res.proof()
    assert proof["filled_by_pair_type"] == MT.PAIR_TYPE_QUOTAS
    assert proof["filled_by_enrichment_band"] == {"near_miss": 300, "other": 300}


def test_joint_maxflow_fails_closed_and_diagnoses():
    counts = dict(MT.CELL_QUOTAS)
    counts["contour-contour|near_miss"] -= 1        # one patient short in the scarcest cell
    res = MT.assign_patients(_availability(counts), seed=1)
    assert not res.feasible and res.achieved_flow == 599
    assert "contour-contour|near_miss" in (res.failure_reason or "")
    diag = res.diagnosis
    assert diag["maximum_achievable_flow"] == 599 and diag["shortfall"] == 1
    assert diag["binding_cells"] == {"contour-contour|near_miss": 1}
    assert diag["patient_conflicts"]["cells_where_demand_exceeds_availability"] == {
        "contour-contour|near_miss": {"quota": 90, "available_patients": 89}}
    assert diag["nearest_feasible_allocation"]["total"] == 599
    with pytest.raises(RuntimeError):
        M.build_primary_manifest([], seed=1, seed_order=2)


def test_joint_quotas_not_satisfiable_by_independent_strata():
    """The failure mode the joint formulation exists to prevent.

    Every pair-type quota is individually satisfiable and every near-miss quota is
    individually satisfiable, but no assignment satisfies both at once: the only patients
    with a contour-contour near-miss pair are also the only ones with a point-contour
    near-miss pair, and there are too few of them to cover 90 + 90.
    """
    avail: dict[str, set[str]] = {}
    for i in range(120):        # 120 patients carry BOTH scarce near-miss cells
        avail[f"N{i:04d}"] = {"contour-contour|near_miss", "point-contour|near_miss",
                              "contour-contour|other", "point-contour|other"}
    for i in range(700):
        avail[f"B{i:04d}"] = {"point-point|near_miss", "point-point|other",
                              "contour-contour|other", "point-contour|other"}
    per_cell = {c: sum(1 for s in avail.values() if c in s) for c in MT.CELL_QUOTAS}
    assert all(per_cell[c] >= MT.CELL_QUOTAS[c] for c in MT.CELL_QUOTAS), \
        "each cell is individually satisfiable -- independent draws would report success"
    res = MT.assign_patients(avail, seed=5)
    assert not res.feasible, "the joint constraint must be detected, not repaired later"
    assert res.diagnosis["shortfall"] == 60
    assert set(res.diagnosis["binding_cells"]) <= {
        "contour-contour|near_miss", "point-contour|near_miss"}


def test_joint_maxflow_handles_overlapping_availability():
    """Patients eligible for several cells: greedy could starve the scarcest."""
    avail = {f"P{i:04d}": {"point-point|near_miss", "contour-contour|near_miss"}
             for i in range(240)}
    avail.update({f"Q{i:04d}": {"point-contour|near_miss"} for i in range(90)})
    avail.update({f"R{i:04d}": {"point-point|other", "point-contour|other",
                                "contour-contour|other"} for i in range(300)})
    res = MT.assign_patients(avail, seed=7)
    assert res.feasible and res.filled == MT.CELL_QUOTAS

    tight = dict(avail)
    for k in [f"P{i:04d}" for i in range(40)]:
        del tight[k]      # 200 patients cannot cover the 120 + 90 near-miss demand
    res2 = MT.assign_patients(tight, seed=7)
    assert not res2.feasible and res2.achieved_flow == 590
    assert res2.diagnosis["shortfall"] == 10


def test_matching_is_input_order_invariant():
    avail = _availability({c: n + 10 for c, n in MT.CELL_QUOTAS.items()})
    items = list(avail.items())
    a = MT.assign_patients(dict(items), seed=42).assignment
    b = MT.assign_patients(dict(reversed(items)), seed=42).assignment
    assert a == b


def test_one_pair_per_patient_enforced_by_capacity():
    res = MT.assign_patients(_availability(), seed=3)
    proof = res.proof()
    assert proof["patient_capacity"] == 1
    assert proof["patient_capacity_validation"]["ok"]
    assert proof["uniqueness_checks"]["quotas_exactly_filled"]
    assert proof["uniqueness_checks"]["pair_type_quotas_exactly_filled"]
    assert proof["uniqueness_checks"]["near_miss_total"] == 300


def test_pinned_patients_consume_quota_and_are_never_double_assigned():
    avail = _availability({c: n + 5 for c, n in MT.CELL_QUOTAS.items()})
    pinned = {p: next(iter(avail[p])) for p in sorted(avail)[:4]}
    res = MT.assign_patients(avail, seed=9, pinned=pinned)
    assert res.feasible
    assert res.filled == MT.CELL_QUOTAS, "pinned units count toward the quota"
    assert not (set(res.assignment) & set(pinned)), "a pinned patient is never re-sampled"
    assert len(res.assignment) + len(pinned) == 600
    for cell, n in res.residual_capacities.items():
        assert n == MT.CELL_QUOTAS[cell] - sum(1 for v in pinned.values() if v == cell)


def test_pin_to_an_ineligible_cell_is_refused():
    avail = _availability()
    victim = sorted(avail)[0]
    bad = next(c for c in MT.CELL_QUOTAS if c not in avail[victim])
    with pytest.raises(MT.InfeasibleAssignmentError):
        MT.assign_patients(avail, seed=1, pinned={victim: bad})


# ---------------------------------------------------------------- manifest -----------
def _pair(pid: str, tag: str, gt: str, d: float, r: float,
          radius_expanded: bool = False) -> POOL.Pair:
    a, b = f"{pid}|{tag}a", f"{pid}|{tag}b"
    return POOL.Pair(
        pair_id=POOL.pair_id(a, b), patient_id=pid, study_uid="S",
        series_uid=f"1.2.{pid}", mark_id_a=a, mark_id_b=b,
        session_index_a=0, session_index_b=1, geometry_type=gt,
        d_mm=d, r_a_mm=r, r_b_mm=r, pool_threshold_mm=max(12.0, 2 * r),
        radius_expanded_only=radius_expanded,
        category_a=X.CAT_NON, category_b=X.CAT_NON,
        max_contour_size_mm=2 * r, slice_thickness_mm=1.0)


def _synthetic_pool(n_per_type: int = 300, n_radius_expanded: int = 0) -> list[POOL.Pair]:
    """Every patient carries pairs in BOTH bands of its own pair type, so the six joint
    cells all have availability and the assignment is a genuine matching."""
    pairs = []
    for gt, r in (("point-point", 0.0), ("point-contour", 3.0), ("contour-contour", 4.0)):
        for i in range(n_per_type):
            pid = f"{gt}-P{i:04d}"
            pairs.append(_pair(pid, "n0", gt, 3.0, r))     # near_miss
            pairs.append(_pair(pid, "n1", gt, 7.5, r))     # near_miss
            pairs.append(_pair(pid, "o0", gt, 1.0, r))     # other
            pairs.append(_pair(pid, "o1", gt, 11.0, r))    # other
    # Radius-expanded-only pairs, deliberately concentrated so that patient 0 carries two
    # of them and therefore forces one into the supplemental census.
    for k in range(n_radius_expanded):
        pid = f"contour-contour-P{max(k - 1, 0):04d}"
        pairs.append(_pair(pid, f"rex{k}", "contour-contour", 17.0 + k, 9.0,
                           radius_expanded=True))
    return pairs


def test_manifest_composition_exact_joint_quotas():
    built = M.build_primary_manifest(_synthetic_pool(), seed=11, seed_order=12)
    c = built.composition
    assert c["n_primary"] == 600
    assert c["distinct_patients"] == 600
    assert c["by_pair_type"] == {"point-point": 240, "point-contour": 180,
                                 "contour-contour": 180}
    assert c["by_cell"] == MT.CELL_QUOTAS
    assert c["near_miss_total"] == 300 and c["near_miss_fraction"] == 0.5
    assert c["near_miss_by_pair_type"] == {"point-point": 120, "point-contour": 90,
                                           "contour-contour": 90}
    assert c["by_enrichment_band"] == {"near_miss": 300, "other": 300}


def test_manifest_one_pair_per_patient():
    built = M.build_primary_manifest(_synthetic_pool(), seed=11, seed_order=12)
    pids = [r["patient_id"] for r in built.private_rows]
    assert len(pids) == len(set(pids)) == 600


def test_selected_pair_lies_in_its_assigned_cell():
    built = M.build_primary_manifest(_synthetic_pool(), seed=11, seed_order=12)
    for row in built.private_rows:
        assert row["assigned_cell"] == f"{row['geometry_type']}|{row['enrichment_band']}"
        assert row["near_miss"] == (row["enrichment_band"] == "near_miss")


def test_all_radius_expanded_pairs_are_reviewed():
    """Every radius-expanded-only pair reaches human review -- primary or census."""
    pool = _synthetic_pool(n_radius_expanded=10)
    built = M.build_primary_manifest(pool, seed=11, seed_order=12)
    census_reviewer, census_private = M.build_census_manifest(
        built.deferred_radius_expanded, built.private_rows, seed=11, seed_order=12)
    audit = M.audit_radius_expanded_coverage(pool, built.private_rows, census_private)

    assert audit["radius_expanded_only_in_pool"] == 10
    assert audit["missing"] == [] and audit["unexpected"] == []
    assert audit["overlap_primary_census"] == [], "no pair is reviewed twice"
    assert audit["pass"]
    assert len(audit["in_primary_manifest"]) + len(audit["in_census_manifest"]) == 10
    # patient 0 carries two of them, so exactly one must have been deferred
    assert len(audit["in_census_manifest"]) == 1
    assert M.audit_blinding(census_reviewer)["pass"]
    assert {r["round"] for r in census_reviewer} == {"radius_expanded_census"}
    # the census manifest never renumbers or reuses a primary identifier
    assert not ({r["review_item_id"] for r in census_reviewer}
                & {r["review_item_id"] for r in built.reviewer_rows})


def test_radius_expanded_pins_survive_the_quota_and_still_fill_it():
    pool = _synthetic_pool(n_radius_expanded=10)
    built = M.build_primary_manifest(pool, seed=11, seed_order=12)
    assert built.composition["by_cell"] == MT.CELL_QUOTAS, \
        "pinning must not distort any joint quota"
    assert built.composition["radius_expanded_only_in_primary"] == 9
    assert built.composition["radius_expanded_only_deferred_to_census"] == 1
    assert built.composition["selection_mode_counts"]["mandatory_radius_expanded"] == 9
    proof = built.matching_proof
    assert proof["pinned_units"] == 9 and proof["total_assigned"] == 600
    assert proof["uniqueness_checks"]["quotas_exactly_filled"]


def test_coverage_audit_fails_when_a_radius_expanded_pair_is_dropped():
    pool = _synthetic_pool(n_radius_expanded=10)
    built = M.build_primary_manifest(pool, seed=11, seed_order=12)
    audit = M.audit_radius_expanded_coverage(pool, built.private_rows, [])
    assert not audit["pass"] and len(audit["missing"]) == 1


def test_manifest_hash_reproducible_under_shuffled_input():
    import random
    pool = _synthetic_pool()
    ref = M.build_primary_manifest(pool, seed=11, seed_order=12)
    for rep in range(5):
        shuffled = list(pool)
        random.Random(rep).shuffle(shuffled)
        alt = M.build_primary_manifest(shuffled, seed=11, seed_order=12)
        assert alt.reviewer_hash == ref.reviewer_hash
        assert alt.private_hash == ref.private_hash


def test_opaque_identifier_stability_and_round_separation():
    a = M.opaque_id("pair-x", 5, "primary")
    assert a == M.opaque_id("pair-x", 5, "primary"), "stable"
    assert a != M.opaque_id("pair-x", 5, "repeat"), "repeat round gets a different id"
    assert a != M.opaque_id("pair-x", 6, "primary"), "seed-dependent"
    assert "pair-x" not in a


def test_reviewer_manifest_has_no_forbidden_columns():
    built = M.build_primary_manifest(_synthetic_pool(), seed=11, seed_order=12)
    audit = M.audit_blinding(built.reviewer_rows)
    assert audit["pass"], audit
    assert audit["forbidden_fields_leaked"] == []
    assert set(built.reviewer_rows[0]) == set(M.REVIEWER_COLUMNS)
    # a private row is deliberately NOT reviewer-safe
    assert not M.audit_blinding(built.private_rows)["pass"]


def test_repeat_subset_size_and_concealment():
    built = M.build_primary_manifest(_synthetic_pool(), seed=11, seed_order=12)
    reviewer, private = M.build_repeat_subset(built.private_rows, seed=11)
    assert len(reviewer) == len(private) == M.N_REPEAT == 120
    primary_ids = {r["review_item_id"] for r in built.reviewer_rows}
    assert not ({r["review_item_id"] for r in reviewer} & primary_ids), \
        "repeat ids must not collide with primary ids"
    assert M.audit_blinding(reviewer)["pass"]
    # linkable only through the private mapping
    assert all("primary_review_item_id" in m for m in private)
    # deterministic
    r2, _ = M.build_repeat_subset(built.private_rows, seed=11)
    assert [r["review_item_id"] for r in reviewer] == [r["review_item_id"] for r in r2]


def test_repeat_subset_is_stratified_over_the_six_joint_cells():
    built = M.build_primary_manifest(_synthetic_pool(), seed=11, seed_order=12)
    _, private = M.build_repeat_subset(built.private_rows, seed=11)
    from collections import Counter
    got = Counter(m["assigned_cell"] for m in private)
    assert set(got) == set(MT.CELL_QUOTAS), "all six cells represented"
    # proportional to the 120/120/90/90/90/90 primary quotas at a 120/600 sampling rate
    assert dict(got) == {c: n // 5 for c, n in MT.CELL_QUOTAS.items()}
    assert sum(1 for m in private if m["near_miss"]) == 60


def test_independent_round_reuses_the_subset_but_not_its_identifiers():
    built = M.build_primary_manifest(_synthetic_pool(), seed=11, seed_order=12)
    repeat_reviewer, repeat_private = M.build_repeat_subset(built.private_rows, seed=11)
    independent = M.build_independent_manifest(repeat_private, seed_order=12)

    assert len(independent) == M.N_REPEAT == 120
    assert M.audit_blinding(independent)["pass"]
    assert {r["round"] for r in independent} == {"independent"}
    ids = {r["review_item_id"] for r in independent}
    assert not (ids & {r["review_item_id"] for r in repeat_reviewer})
    assert not (ids & {r["review_item_id"] for r in built.reviewer_rows})
    # same items underneath, different presentation order
    by_pos = {r["review_item_id"]: r["display_order"] for r in independent}
    assert sorted(by_pos.values()) == list(range(120)), "a total order, no gaps or ties"
    repeat_order = {m["pair_id"]: m["display_order"] for m in repeat_private}
    indep_order = {m["pair_id"]: by_pos[m["independent_item_id"]] for m in repeat_private}
    assert set(repeat_order) == set(indep_order), "identical 120-item subset"
    assert repeat_order != indep_order, "the second reviewer sees a different order"
    assert M.build_independent_manifest(repeat_private, seed_order=12) == independent


# ---------------------------------------------------------------- review store ------
def _store(tmp: str) -> RS.ReviewStore:
    st = RS.ReviewStore(tmp)
    st.register_human_reviewer("reviewer-1", "human reviewer, attested out of band",
                              role="primary_reference")
    return st


def _backdate(st: RS.ReviewStore, round_name: str, reviewer_id: str, days: int) -> None:
    """Rewrite stored timestamps so a washout can be exercised without waiting a week."""
    from datetime import timedelta
    path = st.path_for(round_name, reviewer_id)
    lines = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            ts = RS.datetime.fromisoformat(rec["timestamp_utc"]) - timedelta(days=days)
            rec["timestamp_utc"] = ts.isoformat(timespec="seconds")
            lines.append(json.dumps(rec, sort_keys=True))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def test_only_three_labels_permitted():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        for lab in RS.LABELS:
            st.save_label(review_item_id=f"i-{lab}", reviewer_id="reviewer-1",
                          label=lab, round_name="primary")
        for bad in ("same", "SAME_PHYSICAL_LESION", "yes", "", "probably_same"):
            with pytest.raises(RS.LabelRejected):
                st.save_label(review_item_id="i-x", reviewer_id="reviewer-1",
                              label=bad, round_name="primary")


def test_unregistered_reviewer_cannot_label():
    """No automated source may create a label."""
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        for rid in ("model-v1", "automated-reviewer", "auto", "similarity-algorithm"):
            with pytest.raises(RS.LabelRejected):
                st.save_label(review_item_id="i1", reviewer_id=rid,
                              label="same_physical_lesion", round_name="primary")


def test_storage_is_append_only():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                      label="same_physical_lesion", round_name="primary")
        first = st.save_label(review_item_id="i2", reviewer_id="reviewer-1",
                              label="indeterminate", round_name="primary")
        st.save_label(review_item_id="i2", reviewer_id="reviewer-1",
                      label="different_physical_lesion", round_name="primary",
                      supersedes=first["record_id"])
        recs = st.read_all("primary")
        assert len(recs) == 3, "the revision is appended; the original is retained"
        i2 = [r for r in recs if r["review_item_id"] == "i2"]
        assert {r["label"] for r in i2} == {"indeterminate", "different_physical_lesion"}


def test_duplicate_primary_review_refused():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                      label="same_physical_lesion", round_name="primary")
        with pytest.raises(RS.LabelRejected):
            st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                          label="different_physical_lesion", round_name="primary")


def test_resume_and_multi_reviewer_disagreement_visible():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        st.register_human_reviewer("reviewer-2", "independent human reviewer",
                                   role="independent")
        st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                      label="same_physical_lesion", round_name="independent")
        st.save_label(review_item_id="i1", reviewer_id="reviewer-2",
                      label="different_physical_lesion", round_name="independent")
        assert st.completed_items("independent", "reviewer-1") == {"i1"}
        view = st.adjudicated_view("independent")["i1"]
        assert view["n_reviewers"] == 2 and view["agreement"] is False
        assert len(view["labels_by_reviewer"]) == 2, "both labels retained, none overwritten"


# ------------------------------------------------------ reviewer governance ----------
def test_only_one_primary_reference_reviewer_permitted():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        with pytest.raises(RS.LabelRejected):
            st.register_human_reviewer("reviewer-2", "another human",
                                       role="primary_reference")
        st.register_human_reviewer("reviewer-2", "another human", role="independent")
        assert st.primary_reference_reviewer() == "reviewer-1"
        assert st.role_of("reviewer-2") == "independent"


def test_independent_reviewer_cannot_write_the_primary_reference():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        st.register_human_reviewer("reviewer-2", "second human", role="independent")
        for round_name in ("primary", "radius_expanded_census"):
            with pytest.raises(RS.LabelRejected):
                st.save_label(review_item_id="i1", reviewer_id="reviewer-2",
                              label="same_physical_lesion", round_name=round_name)
        # but the independent audit round is open to them
        st.save_label(review_item_id="i1", reviewer_id="reviewer-2",
                      label="same_physical_lesion", round_name="independent")


def test_unknown_round_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        for bad in ("Primary", "round2", "", "census", "adjudication"):
            with pytest.raises(RS.LabelRejected):
                st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                              label="indeterminate", round_name=bad)


def test_repeat_round_requires_a_seven_day_washout():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        # no primary decisions at all -> washout undefined -> refused (fails closed)
        assert not st.washout_status("reviewer-1")["satisfied"]
        with pytest.raises(RS.LabelRejected):
            st.save_label(review_item_id="r1", reviewer_id="reviewer-1",
                          label="same_physical_lesion", round_name="repeat")

        st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                      label="same_physical_lesion", round_name="primary")
        with pytest.raises(RS.LabelRejected):
            st.save_label(review_item_id="r1", reviewer_id="reviewer-1",
                          label="same_physical_lesion", round_name="repeat")
        assert st.washout_status("reviewer-1")["required_days"] == RS.WASHOUT_DAYS == 7

        _backdate(st, "primary", "reviewer-1", days=8)
        assert st.washout_status("reviewer-1")["satisfied"]
        st.save_label(review_item_id="r1", reviewer_id="reviewer-1",
                      label="different_physical_lesion", round_name="repeat")
        # the repeat answer never overwrites the primary answer
        primary = [r for r in st.read_all("primary") if r["review_item_id"] == "i1"]
        assert len(primary) == 1 and primary[0]["label"] == "same_physical_lesion"


def test_intra_rater_agreement_and_kappa_reported():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        truth = ["same_physical_lesion"] * 6 + ["different_physical_lesion"] * 4
        for i, lab in enumerate(truth):
            st.save_label(review_item_id=f"p{i}", reviewer_id="reviewer-1",
                          label=lab, round_name="primary")
        _backdate(st, "primary", "reviewer-1", days=8)
        repeat = list(truth)
        repeat[0] = "different_physical_lesion"        # one genuine flip
        for i, lab in enumerate(repeat):
            st.save_label(review_item_id=f"r{i}", reviewer_id="reviewer-1",
                          label=lab, round_name="repeat")
        stats = st.paired_agreement("reviewer-1", "primary", "reviewer-1", "repeat",
                                    [(f"p{i}", f"r{i}") for i in range(10)])
        assert stats["n_paired"] == 10 and stats["n_agree"] == 9
        assert stats["raw_agreement"] == pytest.approx(0.9)
        # p_o = 0.90, p_e = 0.6*0.5 + 0.4*0.5 = 0.50  ->  kappa = 0.40 / 0.50 = 0.80
        assert stats["expected_agreement"] == pytest.approx(0.5)
        assert stats["cohens_kappa"] == pytest.approx(0.8)


def test_agreement_helper_never_mutates_stored_labels():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        st.save_label(review_item_id="p0", reviewer_id="reviewer-1",
                      label="indeterminate", round_name="primary")
        before = st.read_all()
        st.paired_agreement("reviewer-1", "primary", "reviewer-1", "repeat", [("p0", "r0")])
        assert st.read_all() == before


def test_no_free_text_field_stored():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        rec = st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                            label="indeterminate", round_name="primary",
                            reason_code="adjacent_structures_unclear")
        assert set(rec) == {
            "record_id", "review_item_id", "reviewer_id", "label", "round", "reason_code",
            "timestamp_utc", "supersedes", "store_version", "label_source"}
        with pytest.raises(RS.LabelRejected):
            st.save_label(review_item_id="i2", reviewer_id="reviewer-1",
                          label="indeterminate", round_name="primary",
                          reason_code="patient John Doe left lung")


def test_progress_summary_reveals_no_threshold_performance():
    with tempfile.TemporaryDirectory() as tmp:
        st = _store(tmp)
        st.save_label(review_item_id="i1", reviewer_id="reviewer-1",
                      label="same_physical_lesion", round_name="primary")
        prog = st.progress("primary", "reviewer-1", 600)
        assert set(prog) == {"round", "reviewer_id", "completed", "total", "remaining",
                             "label_counts", "indeterminate_fraction"}
        blob = json.dumps(prog).lower()
        for banned in ("precision", "recall", "threshold", "tau", "alpha", "merge"):
            assert banned not in blob


# ---------------------------------------------------------------- split validation ---
# The real split manifest is private and is NOT in this repository. These tests exercise
# the validation logic on synthetic splits, so they always run. Verifying the REAL frozen
# split is a separate integration gate: scripts/verify_private_split.py.
def _synthetic_split(n_dev: int = 12, n_test: int = 4, n_folds: int = 3) -> dict:
    dev = [f"SYNTH-{i:04d}" for i in range(n_dev)]
    test = [f"SYNTH-{i:04d}" for i in range(1000, 1000 + n_test)]
    folds = []
    for k in range(n_folds):
        val = dev[k::n_folds]
        folds.append({"train": [p for p in dev if p not in val], "val": val})
    return {"test": test, "folds": folds}


def test_membership_hash_matches_the_protocol_definition():
    """protocol 5.2: SHA-256 of the sorted, newline-joined patient-ID list."""
    import hashlib
    ids = ["B", "A", "C"]
    expected = hashlib.sha256("A\nB\nC".encode()).hexdigest()
    assert SV.membership_hash(ids) == expected
    assert SV.membership_hash(reversed(ids)) == expected, "order-independent"
    assert SV.membership_hash(set(ids)) == expected, "container-independent"


def test_split_validation_accepts_a_valid_disjoint_split():
    r = SV.validate_split(_synthetic_split(), expected_development=12, expected_test=4)
    assert r["ok"], r["problems"]
    assert r["n_development"] == 12 and r["n_test"] == 4
    assert r["development_test_overlap"] == 0


def test_split_validation_rejects_development_test_overlap():
    d = _synthetic_split()
    d["folds"][0]["train"].append(d["test"][0])          # leak one test patient into dev
    r = SV.validate_split(d)
    assert not r["ok"]
    assert any("disjoint at the patient level" in p for p in r["problems"])
    assert r["development_test_overlap"] == 1
    with pytest.raises(SV.SplitValidationError):
        SV.assert_split_valid(d)


def test_split_validation_rejects_duplicate_membership():
    d = _synthetic_split()
    d["test"] = d["test"] + [d["test"][0]]               # duplicate inside locked test
    r = SV.validate_split(d)
    assert not r["ok"] and any("duplicate" in p for p in r["problems"])

    d2 = _synthetic_split()
    d2["folds"][0]["val"] = d2["folds"][0]["val"] + [d2["folds"][0]["val"][0]]
    r2 = SV.validate_split(d2)
    assert not r2["ok"] and any("duplicate" in p for p in r2["problems"])

    d3 = _synthetic_split()
    d3["folds"][1]["train"].append(d3["folds"][1]["val"][0])   # train/val collision
    r3 = SV.validate_split(d3)
    assert not r3["ok"] and any("train and val share" in p for p in r3["problems"])


def test_split_validation_rejects_incorrect_expected_counts():
    d = _synthetic_split()
    r = SV.validate_split(d, expected_development=999)
    assert not r["ok"] and any("development count" in p for p in r["problems"])
    r2 = SV.validate_split(d, expected_test=999)
    assert not r2["ok"] and any("locked-test count" in p for p in r2["problems"])


def test_split_validation_rejects_incorrect_membership_hash():
    d = _synthetic_split()
    r = SV.validate_split(d, expected_test_membership_hash="0" * 64)
    assert not r["ok"]
    assert any("membership hash mismatch" in p for p in r["problems"])
    # and it passes when given the hash it actually computes
    good = SV.membership_hash(d["test"])
    assert SV.validate_split(d, expected_test_membership_hash=good)["ok"]


def test_split_validation_rejects_missing_partitions():
    for broken in ({"folds": []}, {"test": []}, {"test": [], "folds": []}, []):
        r = SV.validate_split(broken)
        assert not r["ok"] and r["problems"]


def test_split_validation_never_emits_a_patient_identifier():
    """A validator that prints the thing it protects is not a control."""
    d = _synthetic_split()
    d["folds"][0]["train"].append(d["test"][0])
    d["test"] = d["test"] + [d["test"][1]]
    r = SV.validate_split(d, expected_development=1, expected_test=1,
                          expected_test_membership_hash="0" * 64)
    blob = json.dumps(r)
    for pid in set(d["test"]) | SV.development_patients(d):
        assert pid not in blob, f"identifier {pid} leaked into the report"


# ------------------------------------------------- private-split integration gate ----
def _verifier():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "..",
                        "scripts", "verify_private_split.py")
    spec = importlib.util.spec_from_file_location("verify_private_split", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_private_verifier_refuses_when_no_manifest_is_supplied():
    """Absence must never be reported as success."""
    mod = _verifier()
    saved = os.environ.pop("LIDC_SPLIT_MANIFEST", None)
    try:
        assert mod.main([]) == 2, "missing input must exit 2, not 0"
    finally:
        if saved is not None:
            os.environ["LIDC_SPLIT_MANIFEST"] = saved


def test_private_verifier_refuses_a_nonexistent_path():
    mod = _verifier()
    with tempfile.TemporaryDirectory() as tmp:
        assert mod.main(["--manifest", os.path.join(tmp, "absent.json")]) == 2


def test_private_verifier_passes_on_a_synthetic_manifest():
    mod = _verifier()
    d = _synthetic_split()
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        rc = mod.main(["--manifest", p, "--expect-development", "12",
                       "--expect-test", "4", "--expect-hash", SV.membership_hash(d["test"])])
        assert rc == 0


def test_private_verifier_exits_nonzero_on_discrepancy():
    mod = _verifier()
    d = _synthetic_split()
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        rc = mod.main(["--manifest", p, "--expect-development", "12",
                       "--expect-test", "4", "--expect-hash", "0" * 64])
        assert rc == 1, "a read manifest that fails checks must exit 1, not 2 and not 0"


def test_frozen_constants_match_the_public_protocol():
    """The constants the integration gate enforces are the ones the protocol publishes."""
    path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "protocol.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert SV.FROZEN_TEST_MEMBERSHIP_SHA256 in text
    assert str(SV.FROZEN_TEST_PATIENTS) in text
    assert str(SV.FROZEN_DEVELOPMENT_PATIENTS) in text
    assert "SHA-256 of the sorted, newline-joined patient-ID list" in text


# ---------------------------------------------------------------- output guard -------
def _build_script():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "..",
                        "scripts", "build_pilot_manifest.py")
    spec = importlib.util.spec_from_file_location("build_pilot_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_output_directory_may_not_be_inside_the_worktree():
    """The private mapping carries patient IDs; it must never land where it can be
    committed. The repository ROOT itself is the case a prefix-only check misses."""
    mod = _build_script()
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    for bad in (repo, repo + os.sep, os.path.join(repo, "manifests"),
                os.path.join(repo, "docs", "out")):
        with pytest.raises(SystemExit):
            mod.resolve_output_dir(bad, repo)
    # a sibling directory whose name merely starts with the repo path is NOT inside it
    ok = mod.resolve_output_dir(repo + "-pilot-out", repo)
    assert ok == os.path.realpath(repo + "-pilot-out")


def test_output_guard_resolves_symlinks_into_the_worktree():
    """A symlink pointing into the repository must not slip past a lexical check."""
    mod = _build_script()
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    with tempfile.TemporaryDirectory() as tmp:
        link = os.path.join(tmp, "sneaky")
        os.symlink(os.path.join(repo, "docs"), link)
        with pytest.raises(SystemExit):
            mod.resolve_output_dir(link, repo)


# ---------------------------------------------------------------- docs vs code -------
def _protocol_text() -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "protocol.md")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_protocol_states_the_frozen_constants_the_code_uses():
    """The public protocol and the implementation must not drift apart."""
    text = _protocol_text()
    assert "`0.2.1-draft`" in text
    assert "2.0 mm <= d(i,j) <= 10.0 mm" in text, "exact near-miss band"
    assert "r_i + r_j > 12 mm" in text, "exact radius-expanded predicate"
    assert str(M.N_PRIMARY) in text and str(M.N_REPEAT) in text
    assert f"{RS.WASHOUT_DAYS}-day washout" in text or "seven-day washout" in text
    assert "human-reviewed operational association reference" in text
    assert "Census veto rule — RATIFIED and FROZEN" in text
    assert "PROPOSED, AWAITING RATIFICATION" not in text, \
        "no rule that consumes labels may remain unratified once labelling can begin"
    for term in ("radiologist, medical expert, or clinical annotator",):
        assert term in text


def test_protocol_names_no_development_patient_in_the_census_table():
    """The radius-expanded conflict table reports counts, not development-set membership."""
    text = _protocol_text()
    section = text.split("#### 4.6.4")[1].split("#### 4.6.5")[0]
    assert "LIDC-IDRI-" not in section, \
        "the census section must not name development patients"
    assert "6 distinct development patients" in section
    assert "**10 pairs**" in section and "**6 patients**" in section
    # every joint quota appears in the amended §4.6.3 table
    for cell, n in MT.CELL_QUOTAS.items():
        assert str(n) in text, f"quota for {cell} not stated in the protocol"


def test_protocol_reports_both_counting_scopes():
    text = _protocol_text()
    for token in ("41,759", "41,675", "1,018", "1,017", "84 marks"):
        assert token in text, f"{token} missing from the scope reconciliation"
    assert "analysis decision, not a parser rule" in text
    assert X.EXPECTED["marks_total"] == 41759
    assert X.EXPECTED_PRIMARY["marks_total"] == 41675
    assert (X.EXPECTED["marks_total"] - X.EXPECTED_PRIMARY["marks_total"]
            == X.EXCLUDED_PANEL_MARK_COUNTS["total"] == 84)


def test_no_reference_labels_exist_in_the_repository():
    """Nothing in the worktree may contain a stored reference decision."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    found = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in {".git", ".venv", "__pycache__", "input", "output",
                                "models", "analysis"}]
        for n in names:
            if n.startswith("labels__") and n.endswith(".jsonl"):
                found.append(os.path.join(dirpath, n))
    assert found == [], f"reference-label files present in the worktree: {found}"


# ---------------------------------------------------------------- UI (synthetic) -----
def test_render_item_synthetic_only():
    with tempfile.TemporaryDirectory() as tmp:
        paths = APP.render_item("opaque123", lambda _: S.synthetic_volume(), tmp)
        assert len(paths) == 3
        names = sorted(os.path.basename(p) for p in paths)
        assert names == ["opaque123__axial.png", "opaque123__coronal.png",
                         "opaque123__sagittal.png"]
        for p in paths:
            assert os.path.getsize(p) > 0
        # filenames encode only the opaque id
        for n in names:
            assert "P1" not in n and "1.3.6" not in n


def test_window_level_is_fixed_and_documented():
    import numpy as np
    assert APP.WINDOW_HU == (-1000.0, 400.0)
    out = APP.window_to_unit(np.array([-2000.0, -1000.0, 400.0, 5000.0]))
    assert out.tolist() == [0.0, 0.0, 1.0, 1.0]
