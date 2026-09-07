# Label Schema

**Status:** draft, version `0.2.1-draft`, 2026-09-04. Derived from a direct survey of the
original LIDC-IDRI annotation XML, not from any third-party wrapper library, and since
corroborated against the LIDC-IDRI reference publication.
Items marked **UNRESOLVED** are deliberately unset and must be fixed before the final data
build.

This document defines what a label *means*. The statistical protocol that consumes these
labels is in [`protocol.md`](protocol.md).

---

## 1. Unit of analysis

The unit of analysis is a **focal candidate**: a location in one CT series that at least one
radiologist reading session marked in some way.

A candidate is **not** a random image crop, **not** a whole scan, and **not** a pre-clustered
consensus nodule. Candidates are built from the union of all explicit reader marks in a series,
so a location marked by only one reader is as much a candidate as one marked by four.

Candidates are never pooled across series. Reader slots are compared only within the series
they belong to.

---

## 2. The four categories

Every candidate carries a **vote distribution over four mutually exclusive categories**, one
vote per reading session in that series.

| # | Category | Meaning |
|---|---|---|
| 1 | `nodule_ge_3mm` | This reader marked a nodule of at least 3 mm here, with a full outline and semantic ratings. |
| 2 | `nodule_lt_3mm` | This reader marked a nodule smaller than 3 mm here, as a single point, with no semantic ratings. |
| 3 | `non_nodule_ge_3mm` | This reader explicitly marked a lesion of at least 3 mm here and judged it **not** a nodule. |
| 4 | `no_mark` | This reader made no mark at this location. Inferred, never read from the file. |

Categories 1–3 are *explicit* — a radiologist recorded them. Category 4 is *inferred* from the
absence of a mark, and its validity depends entirely on the association rule (§5).

### Source definitions, verified

Quoted from Armato et al. 2011 (the LIDC-IDRI reference database publication), verified at
source 2026-08-30:

| Category | Source definition |
|---|---|
| `nodule_ge_3mm` | "any lesion considered to be a nodule with greatest in-plane dimension in the range 3–30 mm regardless of presumed histology" |
| `nodule_lt_3mm` | "any lesion considered to be a nodule with greatest in-plane dimension less than 3 mm that is not clearly benign" |
| `non_nodule_ge_3mm` | "any other pulmonary lesion, such as an apical scar, with greatest in-plane dimension greater than or equal to 3 mm that does not possess features consistent with those of a nodule" |

The same source confirms the recording convention this schema's derivation rules depend on:
for nodules <3 mm "only the lesion's center-of-mass was recorded"; for non-nodules ≥3 mm
"only a center-of-mass mark was stored"; nodules ≥3 mm received detailed outlines across all
CT sections plus subjective characteristic ratings. Four thoracic radiologists read each scan
in a blinded phase followed by an unblinded phase, "without requiring forced consensus".

The structural rules in §3 were reverse-engineered from XML document structure *before* this
publication was consulted, and they match the published protocol exactly.

### What these categories are not

- They are **not** malignancy labels. LIDC malignancy ratings are a reader's *perceived*
  likelihood of malignancy on a 1–5 scale, not pathology. They are retained as metadata and as
  subgroup variables, never as the training target.
- `non_nodule_ge_3mm` does **not** mean "healthy tissue". It means a radiologist saw something
  focal, considered it, and decided it was not a nodule. These are the study's genuine
  look-alike negatives.
- `no_mark` does **not** mean "this reader saw nothing". It means this reader recorded no mark
  that associates with this candidate under the frozen association rule.

---

## 3. Deriving the categories from the source XML

LIDC XML has no category attribute. Category is derived from document structure.

The relevant fragment, in namespace `http://www.nih.gov` (the namespace is mandatory —
unqualified element lookups match nothing):

```
LidcReadMessage
└── readingSession                      one per reader slot
    ├── servicingRadiologistID          opaque; see §4
    ├── unblindedReadNodule
    │   ├── noduleID                    scan-local string
    │   ├── characteristics             optional; may be present but EMPTY
    │   └── roi × 1..88                 one per CT slice
    │       ├── imageSOP_UID            slice key
    │       ├── inclusion               TRUE | FALSE
    │       └── edgeMap × 1..N          xCoord, yCoord (pixel indices)
    └── nonNodule
        ├── imageSOP_UID
        └── locus                       exactly one point
```

### Derivation rules — FROZEN

`nodule_ge_3mm` has **two** admissible forms, A and B. They are not interchangeable and B is
not a general relaxation of A.

| Class | Rule |
|---|---|
| **A. Ordinary `nodule_ge_3mm`** | `<unblindedReadNodule>` whose `<characteristics>` element is present **and has at least one child**, **and** whose ROIs contain more than one `<edgeMap>` point in total. |
| **B. Documented erratum exception** | `<unblindedReadNodule>` with a **multi-point nodule contour** but **empty or absent `<characteristics>`**, where the mark is one of the **exact marks named by an official TCIA erratum** (§3.2). Retained as `nodule_ge_3mm` on erratum authority. |
| `nodule_lt_3mm` | `<unblindedReadNodule>` that is neither A nor B and is marked by a single `<edgeMap>` point. |
| `non_nodule_ge_3mm` | Any `<nonNodule>` element. Always exactly one `<locus>`. |

**Class B must not be generalised to every empty `<characteristics/>` element.** 18 marks in
the corpus carry a self-closing `<characteristics/>`; only the marks explicitly named by an
erratum qualify as class B. All others fall through to `nodule_lt_3mm` or to the ambiguous set.

Two details are load-bearing:

1. **`<characteristics>` can be present but empty.** An `is not None` test misclassifies all 18.
   **An empty `<characteristics/>` is not equivalent to a populated one.**
2. **Class A alone reconciles to pylidc.** Requiring populated characteristics *and* a contour
   yields **6,859** — exactly the row count of `pylidc`'s independently-built annotation
   database. Requiring only non-empty characteristics yields 6,861 and does not reconcile.

### 3.2 The two documented exceptions

TCIA erratum, 2018-06-28. The collection page records that errors exist for two XML files,
`044.xml` and `191.xml`, in which one reader marked a nodule at the ≥3 mm size class but, in
TCIA's words, "neglected to assign ratings for the nodule characteristics"; on 28 June 2018
"the files were updated with an explanation at the point of the error in the XML files".

TCIA therefore **documented** the omission — it did not supply the missing ratings. **The
omission is permanent** and is a property of the annotation, not a defect awaiting a fix.

The two marks, identified by **series UID + session index + noduleID** (never by bare filename —
the basenames `044.xml` and `191.xml` recur across directories for *different* series, and a
filename-keyed rule matches the wrong marks):

| Subject | Series UID (tail) | Session | noduleID | ROIs / points |
|---|---|---|---|---|
| LIDC-IDRI-0305 | `…527162678142285870245028` | 1 | `Nodule 001` | 4 / 105 |
| LIDC-IDRI-0447 | `…525524522225658609808059` | 2 | `Nodule 002` | 3 / 84 |

### Reconciliation gate — mandatory, fail closed

Candidate construction is **not permitted** until all four assertions pass on the corpus
actually in use:

| Assertion | Expected |
|---|---|
| Class A (ordinary) count | **6,859** |
| Class B (documented exceptions) count | **2** |
| Total `nodule_ge_3mm` = A + B | **6,861** |
| Undocumented "no characteristics + contour" marks | **0** |

The fourth assertion is what gives the rule its teeth: it proves the exception is *exactly* the
two erratum marks and has not leaked into a general relaxation.

**Verified 2026-08-31 against the hash-pinned corpus
(`644557a3aa305602609c718b0cae33a93be762e8901a80bcd9df735b0ec6ab90`): all four PASS.**

The parser must re-derive and record these figures, together with the corpus SHA-256 and access
date, rather than trusting a constant. **pylidc's 6,859 remains a regression check for class A
only** — it cannot see class B, the 13,233 `<3 mm` marks, or the 21,663 non-nodules, and is no
longer treated as complete production ground truth.

### Verified counts, both scopes (one selected file per series)

The reconciliation gate is applied at **corpus scope** — every parsed CT series, *including* the
excluded eight-session panel — because its job is to prove the parser reads the XML correctly,
which is independent of any later analysis-scope decision. The **primary-analysis** scope drops
LIDC-IDRI-0566 and its 84 marks. Both are recorded; neither replaces the other. See
[`protocol.md`](protocol.md) §3.2 and §5.1.

| Category | Corpus scope (1,018 series) | Primary-analysis scope (1,017 series) |
|---|---:|---:|
| `nodule_ge_3mm` — class A (ordinary) | 6,859 | 6,855 |
| `nodule_ge_3mm` — class B (documented exceptions) | 2 | 2 |
| `nodule_ge_3mm` — **total** | **6,861** | **6,857** |
| `nodule_lt_3mm` | 13,233 | 13,217 |
| `non_nodule_ge_3mm` | 21,663 | 21,599 |
| Ambiguous, undocumented (see §3.3) | 2 | 2 |
| **Total explicit marks** | **41,759** | **41,675** |

The difference is exactly the excluded panel's 84 marks (4 + 16 + 64). An earlier heading in
this document described the 41,759 figure as excluding LIDC-IDRI-0566; **that was wrong** — the
figure has always been corpus-scope, and the two scopes are now stated separately.

Also verified: reading sessions per series `{3: 1, 4: 1,016, 8: 1}`; `inclusion` values
`{TRUE: 53,700, FALSE: 1,012}`.

### 3.3 Structurally ambiguous marks

**Two** marks have populated `<characteristics>` but only a single point — genuinely ambiguous,
with no erratum covering them:

| Series UID (tail) | Session | noduleID | ROIs / points |
|---|---|---|---|
| `…152156802508672627785405` | 0 | `5117` | 1 / 1 |
| `…021165118974848436095034` | 0 | `77021` | 1 / 1 |

**Handling — FROZEN.** Every candidate touched by one of these is **excluded from the primary
benchmark**. The affected reader vote is **not** silently converted to `no_mark`. Marks and
exclusion reasons are preserved in the internal manifest. A sensitivity analysis using **both**
plausible category assignments is predeclared. The excluded-candidate count is reported in the
cohort-flow table.

**These marks are nevertheless eligible for the association pool** ([`protocol.md`](protocol.md)
§4.6.5, ratified `0.2.1-draft`). Exclusion from the label space and eligibility for pairing are
separate decisions: association is category-agnostic, so making a mark's *physical* pairing
depend on its unresolved *category* would be exactly the coupling the pool predicate exists to
prevent. Two pool pairs involve such a mark; neither was selected into the 600-pair reference
set.

---

## 4. Reader slots and panels

`servicingRadiologistID` takes the values `anon`, `anonymous`, `""`, or an opaque integer. It
carries **no** cross-scan identity.

Therefore:

- Reader slots are **exchangeable within a series** and are indexed only by their position in
  the document (`reader_slot = 0..R-1`).
- Slot *k* in one scan has **no relationship** to slot *k* in another.
- Modelling individual radiologist style, expertise, or bias is impossible with this data and
  is out of scope.

**The number of reading sessions is per-scan and must never be hardcoded to 4:**

| Sessions | Series | Handling — FROZEN |
|---|---|---|
| 3 | 1 (**LIDC-IDRI-0700**) | **Included**, denominator 3 |
| 4 | 1,016 | Included, denominator 4 |
| 8 | 1 (**LIDC-IDRI-0566**) | **Excluded from the primary study** |

LIDC-IDRI-0566 contains two four-reader panels concatenated into one document, with eight
distinct opaque radiologist IDs. Treating it as an eight-reader scan makes its vote entropy
incomparable with every other scan. The exclusion is recorded **before** candidate construction
and reported in the cohort flow.

A panel-splitting sensitivity analysis is permitted later **only** if a deterministic,
independently verifiable grouping rule is found. **Document ordering alone must not be used** —
the apparent 0–3 / 4–7 structure is suggestive, not evidence.

---

## 5. Vote distributions and the `no_mark` rule

For a candidate *i* in a series with `R` reading sessions:

1. Each session contributes **exactly one** vote.
2. A session that has a mark associated with candidate *i* votes for that mark's category.
3. A session with no associated mark votes `no_mark`.
4. **Invariant:** the four vote counts sum to `R`. Asserted in code; fails loudly.

`no_mark` is generated **only after** reader-panel resolution and candidate association —
never before.

Two structural invariants, with **zero tolerance** (not percentage allowances):

- Zero candidates containing more than one mark from the same reading session.
- Zero candidates containing more explicit marks than the scan's valid reader-session count.

Any violation fails the setting or the implementation outright.

The empirical vote distribution is

$$ y_{ik} = \frac{\text{vote count for category } k}{R}, \qquad \sum_k y_{ik} = 1 . $$

### Association is a labelling decision, not plumbing

`no_mark` votes are *manufactured by the association rule*. A loose distance threshold merges
distinct findings and invents agreement; a tight one splits one finding into several candidates
and invents `no_mark` votes. The disagreement variable is therefore directly sensitive to a
parameter that is **not yet frozen**.

**Association thresholds are PROPOSED, not frozen.** LIDC itself publishes no matching
threshold — Armato et al. state that grouping "was performed by visual inspection" — so no
authoritative value exists to adopt. Thresholds will be selected by the development-only pilot
specified in [`protocol.md`](protocol.md) §4.6–4.7 and frozen in a `0.3.0` revision. No default
is assumed meanwhile.

---

## 6. Disagreement measures

**Primary — normalised vote entropy. FROZEN:**

$$ D_i = -\frac{1}{\ln 4} \sum_{k=1}^{4} y_{ik} \ln y_{ik} $$

with the following conventions, all fixed:

- **natural logarithms** (`ln`);
- the mathematical convention **`0 · log 0 = 0`** — zero-probability categories contribute
  exactly zero;
- **no epsilon is added to nonzero probabilities**;
- normalisation by **`ln 4`**, giving `D_i ∈ [0, 1]`.

`D_i = 0` means unanimity; `D_i = 1` means votes spread evenly across all four categories.

The `0 · log 0 = 0` convention replaces the epsilon-smoothing of earlier drafts. Adding an
epsilon would have made `D_i` depend on an arbitrary constant and, because most candidates have
two or three zero-count categories, would have shifted essentially every value — including the
unanimous cases, which must be exactly 0.

**Secondary** — `1 − max_k y_ik`, and mean pairwise categorical disagreement across session
pairs.

**High-disagreement secondary label — FROZEN:** `max_k y_ik ≤ 0.5` — no category holds a strict
reader majority.

**Secondary hard ≥3 mm label — FROZEN:** empirical `nodule_ge_3mm` vote fraction **> 0.5**.
Exact ties are **excluded** from hard-label metrics but **retained** in all distributional,
calibration, and disagreement analyses.

Note the reachable values by denominator: at `R = 4` the attainable maxima are
`{0.25, 0.5, 0.75, 1.0}`, so `max = 0.5` (a 2–2 split) is simultaneously *high disagreement*
and an *excluded tie*. At `R = 3` the attainable maxima are `{1/3, 2/3, 1.0}` and no exact 0.5
occurs. Counts under both denominators appear in the cohort flow.

These describe *empirical reader disagreement*. They are a property of the annotation, not of
any model, and must never be conflated with model epistemic uncertainty — comparing the two is
the study's research question, so collapsing them would make the question circular.

---

## 7. Geometry conventions

- `<edgeMap>` coordinates are **pixel indices** (`xCoord` = column, `yCoord` = row), not
  millimetres. Conversion requires the referenced slice's `ImagePositionPatient`,
  `ImageOrientationPatient`, and `PixelSpacing`.
- Slices are keyed by `<imageSOP_UID>`. `<imageZposition>` is secondary and must not be the sole
  join key.
- **`<inclusion>FALSE` marks an exclusion contour** — a hole or cavity to be subtracted from the
  nodule mask. 1,013 ROIs in the surveyed corpus carry it. Ignoring `inclusion` silently
  produces wrong masks.
- All candidate association and crop geometry operate in millimetres in the patient coordinate
  system. Voxel-index geometry is not used for any scientific decision.

**Per-mark geometry, as used by association** ([`protocol.md`](protocol.md) §4.2):

| Mark type | Centre | Radius |
|---|---|---|
| Contour (`nodule_ge_3mm`) | physical centroid of the 3D inclusion mask **after subtracting `inclusion=FALSE` regions** | volume-equivalent spherical radius `(3V/4π)^(1/3)` from that same physical mask |
| Point (`nodule_lt_3mm`, `non_nodule_ge_3mm`) | physical world coordinate of the recorded locus | **0** — the XML supplies no defensible size estimate |

A radius of 0 for point marks is what the source records, not an approximation. 34,896 of the
41,759 corpus-scope marks are point marks (34,816 of the 41,675 in primary-analysis scope),
which is why any purely size-relative matching criterion is insufficient.

---

## 8. Candidate record fields

```text
candidate_id, patient_id, study_uid, series_uid
physical_center_xyz_mm, physical_extent_xyz_mm
reader_count                          # R for this series
vote_count_nodule_ge_3mm
vote_count_nodule_lt_3mm
vote_count_non_nodule_ge_3mm
vote_count_no_mark
vote_distribution                     # sums to 1
vote_entropy_normalized
source_mark_ids, source_mark_categories, mask_paths_or_ids
ambiguity_flag
association_version, preprocessing_version
split, exclusion_reason
```

The published manifest contains **no image pixels** and follows TCIA data-use terms.

---

## 9. Open items blocking the final data build

1. **Association thresholds** — pending the pilot ([`protocol.md`](protocol.md) §4.6–4.7). The
   only remaining blocker in this document.

Resolved since `0.1.0-draft`: the corpus is hash-pinned and confirmed current; the
reconciliation gate passes fail-closed at 6,859 + 2 = 6,861; the entropy convention is fixed
(natural log, `0·log 0 = 0`, no epsilon, normalise by `ln 4`); reader panels, category rules,
and both secondary labels are frozen.

---

## Provenance

Category semantics and the reader-annotation protocol originate with the LIDC-IDRI reference
database (Armato et al., 2011) and the TCIA collection
(DOI `10.7937/K9/TCIA.2015.LO9QL9SX`, CC BY 3.0); both are cited in the manuscript and
`THIRD_PARTY_NOTICES.md`. The 6,859-mark reconciliation uses `pylidc` (MIT) as an independent
cross-check only — **no label in this project is sourced from it.**

## Amendments

| Version | Date | Change |
|---|---|---|
| `0.1.0-draft` | 2026-08-30 | Initial draft from a direct XML survey. |
| `0.2.1-draft` | 2026-09-04 (rev. b) | **Corrected a quotation.** The 2018-06-28 TCIA erratum had been presented inside quotation marks as "One reader recorded a nodule ≥3 mm but omitted characteristic ratings; files updated with error explanation" — a paraphrase, not TCIA's wording. Replaced with TCIA's exact text ("neglected to assign ratings for the nodule characteristics"; "the files were updated with an explanation at the point of the error in the XML files"), verified against the rebuilt source corpus. The claim it supports — that TCIA documented the omission rather than supplying the ratings — is unchanged and still holds. Found by the `0.2.1-draft` phrase-overlap audit rerun. |
| `0.2.1-draft` | 2026-09-04 (rev. a) | Corrected the verified-counts heading, which described the 41,759-mark total as excluding LIDC-IDRI-0566 when that total has always been **corpus scope, including it**. Counts are now given in **both scopes** side by side — corpus 41,759 over 1,018 series, primary analysis 41,675 over 1,017 — with the 84-mark difference stated explicitly. Recorded that the two structurally ambiguous marks, while excluded from the benchmark label space, remain **eligible for the association pool** (`protocol.md` §4.6.5): exclusion from the label space and eligibility for pairing are separate decisions, and coupling them would make a physical question depend on a category one. No label semantics, category rule, entropy convention, or reconciliation threshold changed. |
| `0.2.0-draft` | 2026-08-31 | Added verified Armato et al. source definitions and recording conventions, corroborating the derivation rules. Split `nodule_ge_3mm` into **class A (ordinary)** and **class B (documented erratum exception)**, with class B restricted to the exact marks named by TCIA erratum and explicitly not generalised to every empty `<characteristics/>`. Added the fail-closed four-assertion reconciliation gate (6,859 A + 2 B = 6,861, plus zero undocumented cases), **verified PASS** against a hash-pinned corpus. Corrected the earlier claim that the two erratum marks would be fixed by re-download — TCIA documented the omission rather than supplying ratings, so it is permanent. Identified the two genuinely ambiguous marks by series UID, session and noduleID. Froze reader-panel handling with subject IDs (LIDC-IDRI-0700 at denominator 3; LIDC-IDRI-0566 excluded). Froze the entropy convention: natural log, `0·log 0 = 0`, no epsilon, normalise by `ln 4`. Froze both secondary labels and noted the reachable-maxima interaction. Added zero-tolerance structural invariants and the per-mark geometry definitions used by association. |
