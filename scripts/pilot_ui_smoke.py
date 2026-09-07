#!/usr/bin/env python3
"""Synthetic-only smoke test for the blinded review interface.

Exercises the full interface against generated volumes: render, serve, resume, append-only
storage, duplicate refusal, and the completion summary. **No LIDC data is touched and no
patient-derived image is written.**

It submits labels for SYNTHETIC items under a clearly-marked synthetic reviewer id, into a
throwaway store. It creates no reference labels for the real pilot.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.pilot import review_app as APP
from src.pilot import review_store as RS
from tests.pilot import synthetic as S

PORT = 8791
SYNTHETIC_REVIEWER = "SYNTHETIC-SMOKE-TEST-NOT-A-REAL-REVIEWER"


def _get(path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=10) as r:
        return json.loads(r.read()) if path.startswith("/api") else r.read()


def _post(path: str, payload: dict):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", method="POST",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> int:
    import threading
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, note=""):
        checks.append((name, bool(ok), note))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  -- ' + note) if note else ''}")

    with tempfile.TemporaryDirectory() as tmp:
        img_dir = os.path.join(tmp, "img")
        items = [f"synthetic{i:02d}opaque" for i in range(4)]
        for i, item in enumerate(items):
            APP.render_item(item, lambda _rid, _i=i: S.synthetic_volume(
                mark_a=(20, 20, 12), mark_b=(20 + 3 * _i, 26, 12)), img_dir)
        rendered = sorted(os.listdir(img_dir))
        check("renders 3 planes per item", len(rendered) == 3 * len(items),
              f"{len(rendered)} files")
        check("image filenames carry only the opaque id",
              all(f.split("__")[0] in items for f in rendered))

        store = RS.ReviewStore(os.path.join(tmp, "review"))
        store.register_human_reviewer(SYNTHETIC_REVIEWER, "synthetic smoke test",
                                     role="primary_reference")

        server = APP.serve(store=store, items=items, reviewer_id=SYNTHETIC_REVIEWER,
                           round_name="primary", image_dir=img_dir, port=PORT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            page = _get("/")
            body = page.decode()
            check("page serves and offers exactly the three labels",
                  all(lab in body for lab in RS.LABELS))
            for banned in ("patient", "series", "session", "distance", "threshold",
                           "category", "entropy", "prediction"):
                if banned in body.lower():
                    check(f"page does not mention {banned!r}", False)
            check("page mentions no identifying/analytic term", True)

            first = _get("/api/next")
            check("next item is opaque-id only",
                  set(first) == {"done", "review_item_id", "images", "completed", "total"},
                  str(sorted(first)))
            check("no forbidden field in the item payload",
                  not (set(first) & {"patient_id", "series_uid", "d_mm", "category"}))

            code, _ = _post("/api/label", {"review_item_id": first["review_item_id"],
                                           "label": "same_physical_lesion"})
            check("accepts a permitted label", code == 200)

            code, err = _post("/api/label", {"review_item_id": first["review_item_id"],
                                             "label": "probably_the_same"})
            check("rejects a label outside the vocabulary", code == 400,
                  err.get("error", "")[:60])

            code, err = _post("/api/label", {"review_item_id": first["review_item_id"],
                                             "label": "different_physical_lesion"})
            check("refuses a duplicate primary decision", code == 400,
                  err.get("error", "")[:60])

            second = _get("/api/next")
            check("resumes on the next undecided item",
                  second["review_item_id"] != first["review_item_id"]
                  and second["completed"] == 1)

            for item in items[1:]:
                _post("/api/label", {"review_item_id": item, "label": "indeterminate"})
            done = _get("/api/next")
            check("reports completion", done.get("done") is True)
            summary = json.loads(done["summary"])
            check("completion summary has no threshold performance",
                  not (set(summary) & {"precision", "recall", "threshold", "auc"}),
                  str(sorted(summary)))

            recs = store.read_all("primary")
            check("append-only: 4 decisions -> 4 records", len(recs) == 4, f"{len(recs)}")
            check("every record is human-sourced",
                  all(r["label_source"] == "human" for r in recs))
            check("no free-text field in any record",
                  all("comment" not in r and "note" not in r for r in recs))

            # -- reviewer governance, exercised end to end ------------------------
            check("intra-rater repeat is blocked before the 7-day washout",
                  not store.washout_status(SYNTHETIC_REVIEWER)["satisfied"])
            try:
                store.save_label(review_item_id=items[0], reviewer_id=SYNTHETIC_REVIEWER,
                                 label="same_physical_lesion", round_name="repeat")
                check("repeat round refuses to open early", False)
            except RS.LabelRejected as exc:
                check("repeat round refuses to open early", True, str(exc)[:60])

            store.register_human_reviewer("SYNTHETIC-SECOND-REVIEWER", "synthetic",
                                          role="independent")
            try:
                store.save_label(review_item_id=items[0],
                                 reviewer_id="SYNTHETIC-SECOND-REVIEWER",
                                 label="same_physical_lesion", round_name="primary")
                check("independent reviewer cannot write the primary reference", False)
            except RS.LabelRejected:
                check("independent reviewer cannot write the primary reference", True)
            store.save_label(review_item_id=items[0],
                             reviewer_id="SYNTHETIC-SECOND-REVIEWER",
                             label="different_physical_lesion", round_name="independent")
            check("independent round accepts the second reviewer",
                  len(store.read_all("independent")) == 1)
            check("the second reviewer never altered a primary record",
                  len(store.read_all("primary")) == 4)
        finally:
            server.shutdown()
            server.server_close()

    failed = [n for n, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    print("NOTE: labels above are synthetic-fixture decisions in a throwaway store. "
          "ZERO reference labels were created for the real pilot.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
