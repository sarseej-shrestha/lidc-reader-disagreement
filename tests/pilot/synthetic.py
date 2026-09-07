"""Synthetic fixtures for the pilot tests.

Everything here is generated from code. **No LIDC XML, no DICOM, and no patient-derived
image is present in the repository, the tests, or git history.**
"""

from __future__ import annotations

import os
import textwrap

NS = 'xmlns="http://www.nih.gov"'


def _edge(x: int, y: int) -> str:
    return f"<edgeMap><xCoord>{x}</xCoord><yCoord>{y}</yCoord></edgeMap>"


def contour_roi(z: float, cx: int, cy: int, r: int = 4, inclusion: str = "TRUE",
                sop: str | None = None) -> str:
    pts = "".join(_edge(cx + dx, cy + dy) for dx, dy in
                  ((-r, 0), (0, -r), (r, 0), (0, r), (-r + 1, 1)))
    return (f"<roi><imageZposition>{z}</imageZposition>"
            f"<imageSOP_UID>{sop or f'1.2.3.{int(z)}'}</imageSOP_UID>"
            f"<inclusion>{inclusion}</inclusion>{pts}</roi>")


def point_roi(z: float, cx: int, cy: int, sop: str | None = None) -> str:
    return (f"<roi><imageZposition>{z}</imageZposition>"
            f"<imageSOP_UID>{sop or f'1.2.3.{int(z)}'}</imageSOP_UID>"
            f"<inclusion>TRUE</inclusion>{_edge(cx, cy)}</roi>")


CHARACTERISTICS = ("<characteristics><subtlety>4</subtlety>"
                   "<internalStructure>1</internalStructure>"
                   "<calcification>6</calcification><sphericity>3</sphericity>"
                   "<margin>5</margin><lobulation>2</lobulation>"
                   "<spiculation>1</spiculation><texture>5</texture>"
                   "<malignancy>3</malignancy></characteristics>")

EMPTY_CHARACTERISTICS = "<characteristics/>"


def nodule(nodule_id: str, rois: str, characteristics: str = CHARACTERISTICS) -> str:
    return (f"<unblindedReadNodule><noduleID>{nodule_id}</noduleID>"
            f"{characteristics}{rois}</unblindedReadNodule>")


def non_nodule(nn_id: str, z: float, x: int, y: int) -> str:
    return (f"<nonNodule><nonNoduleID>{nn_id}</nonNoduleID>"
            f"<imageZposition>{z}</imageZposition>"
            f"<imageSOP_UID>1.2.3.{int(z)}</imageSOP_UID>"
            f"<locus><xCoord>{x}</xCoord><yCoord>{y}</yCoord></locus></nonNodule>")


def session(body: str, radiologist: str = "anon") -> str:
    return (f"<readingSession><annotationVersion>3.12</annotationVersion>"
            f"<servicingRadiologistID>{radiologist}</servicingRadiologistID>"
            f"{body}</readingSession>")


def lidc_xml(series_uid: str, sessions: list[str], study_uid: str = "1.9.9.9") -> str:
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <LidcReadMessage uid="1.0.0.{abs(hash(series_uid)) % 10 ** 6}" {NS}>
          <ResponseHeader>
            <Version>1.8</Version><MessageId>SYNTH</MessageId>
            <TaskDescription>Second unblinded read</TaskDescription>
            <SeriesInstanceUid>{series_uid}</SeriesInstanceUid>
            <ResponseDescription>1 - Reading complete</ResponseDescription>
            <StudyInstanceUID>{study_uid}</StudyInstanceUID>
          </ResponseHeader>
          {''.join(sessions)}
        </LidcReadMessage>
        """)


def idri_xml(series_uid: str) -> str:
    """A radiography document: different root tag AND different namespace."""
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <IdriReadMessage xmlns="http://www.nih.gov/idri">
          <ResponseHeader><SeriesInstanceUid>{series_uid}</SeriesInstanceUid></ResponseHeader>
        </IdriReadMessage>
        """)


def write(tmp: str, name: str, content: str) -> str:
    path = os.path.join(tmp, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def synthetic_volume(shape=(48, 48, 24), spacing=(1.0, 1.0, 1.0),
                     mark_a=(20, 20, 12), mark_b=(28, 26, 12)):
    """A synthetic HU volume with two blobs. Contains no patient data."""
    import numpy as np
    rows, cols, slices = shape
    vol = np.full(shape, -900.0, dtype="float32")
    rr, cc, ss = np.meshgrid(np.arange(rows), np.arange(cols), np.arange(slices),
                             indexing="ij")
    for centre, hu in ((mark_a, 60.0), (mark_b, 20.0)):
        d = ((rr - centre[0]) ** 2 + (cc - centre[1]) ** 2 + (ss - centre[2]) ** 2) ** 0.5
        vol[d < 4] = hu
    return {"volume": vol, "spacing_mm": spacing, "mark_a": mark_a, "mark_b": mark_b}
