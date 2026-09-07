# Study Protocol

**Status:** `0.2.1-draft` — a **timestamped pre-pilot design snapshot**, 2026-09-04.
**This is not the Milestone 1 freeze.** No locked-test evaluation may occur under a draft protocol.

Three separate gates remain open, and none of them is closed by this version:

| Gate | What it closes | State |
|---|---|---|
| **1. Pre-pilot documentation gate** | full-text bibliography verification and the phrase-overlap/attribution audit | **PASS** — both components rerun in full at `0.2.1-draft` against all 17 cited sources (§15.A) |
| **2. Association freeze** | the §4.5 threshold grid, via the §4.6 pilot **and** the §4.7 100-candidate cluster audit | **OPEN** — thresholds are **PROPOSED, not frozen** |
| **3. Preprocessing / field-of-view freeze** | the §3.5 64 mm field of view, via the development-only truncation audit **after candidate construction** | **OPEN** — the specification is declared, **not frozen** |

Association thresholds are **not frozen**. The preprocessing field of view is **not frozen**.
**Milestone 1 is not complete.** Gate 2 closes in a `0.3.0` revision; gate 3 in a later revision;
`1.0.0` denotes the Milestone 1 freeze once all three are closed.

**State of the pilot at this revision.** The reference-set manifests are generated, hashed and
blinded. **Zero reference labels exist.** No pairwise decision has been recorded by any person
or process, no threshold performance has been computed, no threshold has been selected, and the
§4.7 cluster audit has not been run. Every rule that will consume those labels — including the
§4.6.4 census veto — was **frozen before the first label was created**.

Label semantics are defined in [`label_schema.md`](label_schema.md).

---

## 1. Study type and intended use

A **retrospective, single-dataset, methodological study** on the public LIDC-IDRI collection.

This is research software. It is **not** a clinical device, has no regulatory clearance, and
must not be used for diagnosis, screening, triage, or any clinical decision. No claim of
clinical utility is made anywhere in this project.

---

## 2. Research question

> Can uncertainty estimates from a candidate-level CT model identify focal pulmonary
> abnormalities for which LIDC-IDRI radiologists disagree about noduleness?

The design deliberately makes the modelled target and the disagreement target the **same
construct**: the model predicts a distribution over reader votes, and disagreement is
measured on that same vote distribution.

### Working contribution statement

> A reproducible candidate-level benchmark that preserves post-unblinded LIDC reader vote
> distributions, and an evaluation of whether several uncertainty estimators identify
> disagreement about pulmonary noduleness under patient-disjoint validation.

This claim will not be strengthened until every cited source is verified at full text (§15).

### Prior art and attribution — explicit

**No method in this project is novel.** The following are established prior work, used here as
comparative baselines or as replication in a different label setting:

| Component | Prior work |
|---|---|
| Residual architectures (ResNet-18 backbone) | He et al., *Deep Residual Learning for Image Recognition*, CVPR 2016. The 18-layer residual variant is evaluated in that paper (Table 1; Table 2; Fig. 4, "ResNet-18"), so the specific backbone is attributable to it. |
| Multi-view 2D CT nodule modelling | Setio et al., IEEE Trans Med Imaging 35(5):1160–1169, 2016 — that paper extracts 2-D patches from, in its words, "nine symmetrical planes of a cube", each patch covering a 50 × 50 mm bounding box at 64 × 64 px, and combines the streams by late-fusion, committee-fusion, or both. **That paper also evaluates 1-view and 3-view configurations** (Section VI reports runtimes for ConvNets with 1, 3 and 9 views). Our three-view model is therefore one of the configurations that paper already tested, and our fixed-physical-patch extraction follows its convention — **neither is novel here.** |
| MC dropout | Gal & Ghahramani, ICML 2016 — T stochastic forward passes averaged ("MC dropout"), interpreted as approximately integrating over the model's weights. That paper states its own limit: the predictive distribution "is expected to be highly multi-modal, and the above approximations only give a glimpse into its properties." |
| Deep ensembles | Lakshminarayanan et al., NIPS 2017 — Algorithm 1 gives "Recommended default values are M = 5". Our five-member size follows that recommendation; it is **not** an independent choice of ours. Ovadia et al. 2019 independently report that "relatively small ensemble size (e.g. M = 5) may be sufficient". |
| Aleatoric/epistemic terminology and its limits | Kendall & Gal, NIPS 2017 |
| Temperature scaling; ECE | Guo et al., ICML 2017 |
| Uncertainty under dataset shift | Ovadia et al., NeurIPS 2019 — benchmarks temperature scaling explicitly and finds "nearly all other methods (except vanilla) perform better than the state-of-the-art post-hoc calibration (Temperature scaling) in terms of Brier score under shift", and that its "ECE increases significantly as the shift increases". Deep ensembles "seem to perform the best across most metrics and be more robust to dataset shift". |
| Grad-CAM | Selvaraju et al., ICCV 2017 — gradients average-pooled into "neuron importance weights", then "a ReLU to the linear combination of maps", computed at the **last convolutional layer**, which that paper justifies as "the best compromise between high-level semantics and detailed spatial information". Our use of an earlier layer is a documented deviation, not that paper's method (§11). |
| Saliency randomisation controls | Adebayo et al., NeurIPS 2018 |
| Patient-level splitting, clustered bootstrap, permutation testing, risk-coverage | standard methodology; not attributed to this project |
| **MC dropout / deep ensembles / their comparison / uncertainty-based referral on lung CT** | **Zahari, Cox & Obara, Computers in Biology and Medicine 172:108324, 2024** |

**Explicitly: no novelty is claimed for uncertainty-based referral itself.**

### Closest prior art, verified at full text

**Zahari, Cox & Obara 2024** compares MC dropout, deep ensembles and ensemble MC dropout on 3D CT
lung nodules with an uncertainty-threshold referral analysis (referral raises accuracy to 0.959).
Its cohort is built by keeping "only nodules annotated by **at least three of the four
radiologists**" with diameter ≥3 mm, and its label is the **average malignancy score thresholded
at 3**, with "nodules with an average of 3 were removed". It reports entropy and standard
deviation for **correctly versus incorrectly** classified cases. It does not measure reader
disagreement, does not preserve individual reader votes, and reports no calibration analysis.

**Consequence.** That design removes the signal this project targets — twice: by filtering to the
high-agreement subset, and by deleting the most ambiguous cases. The overlap with this project is
therefore confined to *method*, not *question*. The uncertainty estimators and the referral
analysis here are **replication of established methods in a new label setting**; the proposed
contribution is the physically reconstructed four-category reader-vote benchmark and the direct
uncertainty-versus-reader-disagreement evaluation.

**Liao et al. 2021** (verified at full text) partitions LIDC nodules by annotation reliability
into consistent, inconsistent and low-reliable sets, but targets **malignancy**, considers only
nodules ≥3 mm, excludes non-nodules, reduces each set to single labels, and performs no
uncertainty-versus-disagreement evaluation.

---

## 3. Data

### 3.1 Source, citation, and corpus version

LIDC-IDRI CT series and their original post-unblinded annotation XML, from The Cancer
Imaging Archive.

- **DOI:** `10.7937/K9/TCIA.2015.LO9QL9SX`
- **Licence:** CC BY 3.0
- **Required data citation:** Armato III, S. G., et al. (2015). *Data From LIDC-IDRI*
  [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX
- Use abides by TCIA's Data Usage Policy.

**Annotation corpus, hash-pinned:**

| Field | Value |
|---|---|
| Source URL | `https://www.cancerimagingarchive.net/wp-content/uploads/LIDC-XML-only.zip` |
| Access date | **2026-08-31T06:08:16Z** |
| Archive SHA-256 | `644557a3aa305602609c718b0cae33a93be762e8901a80bcd9df735b0ec6ab90` |
| Archive size | 9,034,311 bytes |
| Extracted `.xml` files | 1,319 |
| `LidcReadMessage` (CT) | 1,036 |
| `IdriReadMessage` (radiography, excluded) | 283 |
| Distinct CT `SeriesInstanceUid` | 1,018 |

No third-party mirror was used as a source.

Every distributed annotation file carries `TaskDescription = "Second unblinded read"`, so the
post-unblinded reads are the only reads available and no blinded-read filtering is required.

### 3.2 Annotation source of truth

The **standalone** LIDC XML corpus. It covers exactly the 1,018 CT series present in the
reference annotation database — no gaps, no extras — and is a strict superset of the copies
embedded in the DICOM tree, with all 918 shared series byte-identical.

Files whose root element is `{http://www.nih.gov/idri}IdriReadMessage` are radiography reads,
not CT, and are excluded **by root-tag check, never by filename**.

`pylidc` is used **only** as an independent reconciliation and regression reference (§4.1).
It supplies no production label.

#### Two counting scopes — RATIFIED at `0.2.1-draft`

Every mark count in this document belongs to exactly one of two scopes, and the two are
reported side by side rather than one replacing the other.

| Scope | Contents | What it is for |
|---|---|---|
| **Corpus / parser reconciliation** | **all 1,018 CT series** and **all 41,759 marks**, including the excluded eight-session panel | proving the parser reads the XML correctly |
| **Primary analysis** | **1,017 series** and **41,675 marks** — LIDC-IDRI-0566 and its **84 marks** removed (§5.1) | everything downstream: pairing, candidates, labels, modelling |

```
corpus 41,759  −  excluded panel 84  =  primary analysis 41,675
       (4 nodule_ge_3mm + 16 nodule_lt_3mm + 64 non_nodule_ge_3mm)
```

**The eight-session exclusion is an analysis decision, not a parser rule.** The parser
extracts LIDC-IDRI-0566's marks in full and flags the series; the flag is what removes it
downstream. Applying the reconciliation gate at corpus scope therefore keeps that gate a pure
parser check, independent of any later analysis-scope decision — which is exactly why the two
numbers differ, and why the corpus figures are **not** replaced by the primary ones anywhere in
this document.

Both scopes are asserted in code (`assert_reconciled`, `EXPECTED` and `EXPECTED_PRIMARY`), and
both fail closed.

| Scope | series | `ge3` (A + B) | `lt3` | `non_nodule` | ambiguous | total |
|---|---:|---:|---:|---:|---:|---:|
| Corpus | 1,018 | 6,859 + 2 = **6,861** | 13,233 | 21,663 | 2 | **41,759** |
| Primary analysis | 1,017 | 6,855 + 2 = **6,857** | 13,217 | 21,599 | 2 | **41,675** |

### 3.3 Official corrections

Eight errata are published for this collection; all were verified at source on 2026-08-31 and
checked against the hash-pinned corpus.

| # | Erratum | Affected | Date | Handling |
|---|---|---|---|---|
| 1 | Inconsistent spiculation/lobulation rating systems across 5 sites in ~100 of the initial 399 cases | ~100 cases | — | Does not affect the four-category label space. **Spiculation and lobulation are not comparable across sites** and are excluded as subgroup variables unless the affected cases are identified. |
| 2 | Reader order is **not** consistent between scans; XML cannot compare individual radiologists across cases | all | — | Official basis for the exchangeable-reader-slot rule (`label_schema.md` §4). |
| 3 | Rating-scale ordering: lobulation and spiculation are `1=none` to `5=marked` | all | 2010-03 | Recorded; relevant only if those ratings are used. |
| 4 | LIDC-IDRI-0101 XML replaced with a corrected version; old version retained for audit | LIDC-IDRI-0101 | **2012-03-21** | Resolves supersession — §3.4. |
| 5 | One reader recorded a nodule ≥3 mm but **omitted characteristic ratings**; files updated with an error explanation | `044.xml` (LIDC-IDRI-0305), `191.xml` (LIDC-IDRI-0447) | **2018-06-28** | **The two documented exceptions.** TCIA documented the omission; it did not supply the missing ratings. The omission is permanent. Handled by the category rule in `label_schema.md` §3. |
| 6 | Incorrect SOP Instance UID at position 1420, corrected | LIDC-IDRI-0396 (`139.xml`) | **2018-06-28** | Verified: all 13 annotation-referenced SOP UIDs resolve against the series' 112 DICOM slices. |
| 7 | `internalStructure` assigned value **5**, for which no category exists — invalid | LIDC-IDRI-0510 (`187/255.xml`) | — | Confirmed present (values `{1: 21, 5: 1}`). Parsers **must reject `internalStructure == 5`** as invalid. Does not touch the label space. |
| 8 | Collection includes unintended **duplicate scans for 8 patients** | LIDC-IDRI-0132, 0151, 0315, 0332, 0355, 0365, 0442, 0484 | — | Confirmed: 2 scans each. These are the cases the deterministic series-selection rule must resolve (§3.5). |

The corpus is confirmed current: the archive downloaded 2026-08-31 is byte-identical to the
previously held copy (1,319 files, 0 changed).

### 3.4 Deterministic source selection

Seven series have more than one annotation file (1,036 files → 1,018 series). Resolution:

1. Group by `SeriesInstanceUid`.
2. Compare a canonical hash of the **annotation payload only** — the concatenated
   `<readingSession>` subtrees, ignoring the root `uid` attribute and the entire
   `<ResponseHeader>`. Hashing the whole document is **insufficient**: four series differ only
   in where `<StudyInstanceUID>` sits inside `<ResponseHeader>`, which a document-level hash
   misreports as a genuine content difference.
3. All payload hashes equal → take the lexicographically smallest path.
4. Genuine payload difference → resolve **only** by official TCIA erratum (§3.3).
5. Genuine difference with no corresponding erratum → **exclude the series** from the primary
   benchmark, retain all versions and hashes internally, predeclare a sensitivity analysis
   over each version.

Under this rule: 6 series are duplicates or cosmetic variants, and **exactly one**
(LIDC-IDRI-0101) has a genuine difference, resolved by erratum 4. **No series requires human
judgement.**

Precedence is **never** taken from filename ordering, `MessageId`, `DateService`, or our own
judgement of which annotation looks more plausible.

For LIDC-IDRI-0101 the corrected file is canonical on the authority of TCIA's 2012-03-21
notice. The manifest records both filenames, both SHA-256 hashes, the payload difference, the
subject ID, the series UID, and the official correction date.

### 3.5 Series selection and preprocessing

#### Duplicate timepoints — FROZEN

Eight subjects have two annotated CT timepoints each (erratum 8): LIDC-IDRI-0132, 0151, 0315,
0332, 0355, 0365, 0442, 0484.

**Both timepoints are included.** Rules:

1. Both remain under the **same `patient_id`**.
2. Both **always** belong to the same development fold, or both to the locked-test partition.
   Never split across partitions.
3. **Association operates within a single series/timepoint only** — never across timepoints. A
   lesion visible at both timepoints yields two candidates, and they are not merged.
4. `candidate_id` includes `patient_id`, `study_uid`, **and** `series_uid`, so same-lesion
   candidates from different timepoints are distinguishable and never silently collapsed.
5. Bootstrap and permutation resampling remain **clustered by patient**, so both timepoints move
   together and the repeated lesion cannot inflate apparent precision.
6. Subgroup tables report **patients, scans, and candidates as three separate counts.**

**Selection by image quality, candidate count, or downstream performance is prohibited.** Choosing
the "better" scan would be a performance-driven data decision, which is exactly what the protocol
exists to prevent — and there is no defensible a-priori rule for which timepoint is canonical.

A test asserts that **all series belonging to one subject receive the same split label**; it fails
if any subject's timepoints are separated. Because both timepoints of one subject are correlated,
treating them as independent observations would understate uncertainty — rule 5 is what prevents
that, and it is why patient-level clustering is required rather than merely convenient.

#### Primary preprocessing specification — DECLARED (not yet frozen: gate 3)

| Parameter | Value |
|---|---|
| Orientation | canonical physical orientation |
| Resampling | **1.0 mm isotropic** |
| Physical field of view | **64 × 64 × 64 mm** |
| Output shape | **64 × 64 × 64 voxels** |
| Crop centre | the associated candidate's **physical centre** |
| Image interpolation | **linear** |
| Mask interpolation | **nearest-neighbour** |
| HU clipping | **[−1000, 400]** |
| Intensity scaling | **linear from the clipped interval to [0, 1]** |
| Primary input | **raw windowed** |
| CLAHE | **declared ablation only** |
| Per-scan normalisation | **prohibited** — it would destroy the fixed HU interpretation |

Exclusion contours (`inclusion = FALSE`) are subtracted from nodule masks. Mask alignment is
verified after every spatial transform.

**The 64 mm field of view is a protocol choice, not a claimed optimum**, and this preprocessing is
not novel: physically-defined patch extraction for CT nodule models is established in Setio et al.
2016, and the multi-view representation is prior art (§2).

#### Truncation audit — required before training

1. Audit **all development contour candidates** for crop truncation.
2. Require **≥99%** to retain the complete union mask **plus a 5 mm physical margin**.
3. Report truncation by candidate size, category, voxel spacing, and scan.
4. **If the 99% rule fails, large candidates are NOT excluded to preserve the 64 mm box.**
   Instead, prepare a protocol amendment selecting a **larger fixed physical field of view**
   before training, freeze the amended field of view, and rerun preprocessing validation.

Excluding large candidates to protect a chosen crop size would silently bias the cohort toward
small lesions — a data decision driven by a preprocessing convenience, which is prohibited.

For **point marks** (`nodule_lt_3mm`, `non_nodule_ge_3mm`) physical extent is **unavailable** —
the source records only a centre of mass — so no truncation statement is possible. The centred crop
supplies **32 mm of nominal context in each axis** from the mark centre, and that is what is
reported; it is not an extent claim.

#### Required synthetic geometry tests

- 1 mm isotropic resampling reproduces expected voxel dimensions;
- physical crop dimensions match the declared field of view;
- image and mask remain aligned after orientation, resampling and cropping;
- HU clipping and [0,1] scaling reproduce hand-calculated values;
- `inclusion=FALSE` regions are correctly subtracted from the union mask;
- index → world → index round-trip within a declared tolerance.

All six run on synthetic fixtures with no patient data, in CI.

---

## 4. Candidates, association, and the threshold pilot

Candidates are built from the union of all explicit reader marks in a series. Each carries a
four-category vote distribution over `nodule_ge_3mm`, `nodule_lt_3mm`, `non_nodule_ge_3mm`,
`no_mark`, with one vote per reading session, summing to that series' session count. Full
definitions: [`label_schema.md`](label_schema.md).

### 4.1 Why this is the study's most sensitive parameter

Association manufactures the `no_mark` votes the primary outcome is computed from. A false
merge collapses two findings into one candidate and **invents reader agreement**, lowering
reader-vote entropy. A false split fabricates `no_mark` votes and **invents disagreement**.
Both corrupt the primary disagreement variable directly.

**LIDC publishes no matching threshold.** Armato et al. 2011, verified at source:

> "Marks considered to represent the same physical nodule within the scan were grouped
> together, recognizing that the same lesion could have been assigned marks representing
> different lesion categories by different radiologists. **Grouping was performed by visual
> inspection.**"

The same source describes that inspection as a subjective judgement about whether the marked
lesions were contiguous in three dimensions. No distance, overlap, or size criterion is given
anywhere.

Two consequences. First, no authoritative number exists to adopt; the threshold grid must
rest on physical geometry, and any figure from elsewhere is a downstream convention. Second,
the same sentence establishes that LIDC itself grouped marks **across categories** — so
association here is **category-agnostic**, and categories are never inputs to the distance
function.

Two derivative conventions were examined and **both rejected as the rule**:

- `pylidc.Scan.cluster_annotations` uses connected components with `tol = pixel_spacing`,
  shrinking by `factor=0.9` to `min_tol=0.1` whenever a cluster exceeds four annotations.
  Connected components is exactly the chain-merging this protocol prohibits, and its
  documented "cannot be automatically reduced" exit is that failure surfacing. Retained only
  as a reconciliation reference.
- LUNA16's evaluation criterion — "a candidate should be located within a distance R of the
  nodule center, where R is set to the diameter of the nodule divided by 2" — motivates a
  size-relative term but is **undefined for point-to-point pairs**. Point marks are 34,896 of
  the 41,759 corpus-scope marks, and 34,816 of the 41,675 in primary-analysis scope (§3.2).

### 4.2 Geometry definitions

All geometry in millimetres, patient coordinate system, after orientation normalisation.

**Contour marks** (≥3 mm nodules):
- centre = physical centroid of the 3D inclusion mask **after subtracting `inclusion=FALSE`
  regions**;
- radius = volume-equivalent spherical radius `r = (3V/4π)^(1/3)` computed from that same
  physical mask.

**Point marks** (<3 mm nodules, non-nodules):
- centre = physical world coordinate of the recorded locus;
- radius = **0**, because the XML supplies no defensible size estimate. This is what the
  source records, not an approximation.

**For every pair:**
```
distance            = 3D Euclidean centre distance, patient physical mm
threshold τ(i,j)    = max(τ_floor, α · (r_i + r_j))
normalized distance = distance / τ(i,j)
```

### 4.3 Clustering: constrained agglomerative complete linkage

- Cluster distance = **maximum** normalized distance over all cross-cluster mark pairs.
- Merge only when that maximum is **≤ 1**.
- **Never** merge two clusters if the result would repeat a reading session.
- At each step choose the eligible merge with the **lowest** complete-linkage distance.
- Final tie-break on stable mark IDs, making the result deterministic.
- Invariance across shuffled input orders is asserted by test.

Single-linkage and connected-components clustering are excluded a priori.

### 4.4 Structural invariants — zero tolerance

These are **invariants, not tolerances**. Any violation fails the setting or the
implementation outright; there is no percentage allowance.

1. Zero candidates containing more than one mark from the same reading session.
2. Zero candidates containing more explicit marks than the scan's valid reader-session count.
3. Exact input-order invariance.
4. Exact deterministic output for a fixed manifest and configuration.
5. No `no_mark` generated before reader-panel resolution **and** candidate association.

### 4.5 Proposed threshold grid — PROPOSED, NOT FROZEN (gate 2)

```
α        ∈ {0, 0.5, 1.0}
τ_floor  ∈ {2, 3, 4, 5, 6} mm
```
15 settings. **The grid is fixed in advance: no setting may be added or removed after pilot
performance is seen.**

Justification is physical, not tuned. LIDC's own size classes anchor it — ≥3 mm nodules span
3–30 mm greatest in-plane dimension, and point-marked lesions are <3 mm, so under ~1.5 mm true
radius. Slice thickness across LIDC ranges ~0.6–5 mm, so two readers marking the same sub-3 mm
lesion can legitimately land on adjacent slices, separated in z by one slice thickness from
reconstruction alone; a `τ_floor` below ~2 mm would systematically false-split such pairs as a
spacing artefact. At the upper end, 6 mm exceeds twice the radius of any point-marked lesion,
beyond which the criterion loses geometric motivation for point pairs and false-merge risk
climbs steeply. `α ∈ {0.5, 1.0}` brackets the LUNA16 convention where size exists.

For every setting the resulting **threshold distribution** is reported, specifically flagging
point-to-contour and contour-to-contour pairs receiving unusually large physical thresholds,
so false-merge behaviour can be inspected.

Per-setting results are additionally stratified by slice thickness (≤1.25 / 1.25–2.5 / >2.5 mm).
If the selected setting behaves inconsistently across those strata, an **anisotropic**
tolerance tied to slice spacing is the predeclared fallback *formulation* — not a post-hoc
rescue of the isotropic one.

### 4.6 Pilot — fixed reference set

Development patients only. **Locked-test patients are not sampled, associated, or inspected.**

#### 4.6.1 Pair-pool predicate — FROZEN

A cross-session pair is eligible for the reference-set sampling pool **if and only if**

```
d(i,j) <= max(12 mm, r_i + r_j)
```

where `d(i,j)` is the Euclidean distance between physical mark centres, `r` is the
volume-equivalent spherical radius for contour marks, and `r = 0` for point marks (§4.2).

Two marks from the **same reading session** are never a pair.

This pool is deliberately a **strict superset** of every pair any grid setting could merge, since
the maximum grid threshold is `max(6 mm, r_i + r_j)`. The 12 mm floor — twice the largest
`τ_floor` — supplies adversarial near-miss negatives that no setting merges.

The predicate is **conjunctive on distance**: the `r_i + r_j` term raises the bound only for pairs
whose marks are physically large. It does **not** admit every pair containing a large contour
regardless of distance. Two 25 mm-apart marks are excluded even if one is large, unless the
combined radii themselves exceed 25 mm.

**Reader agreement, category composition, and model output play no part in pool construction.**

#### 4.6.2 Verified pool counts

Computed 2026-08-31 over development patients only, on the hash-pinned corpus, with
LIDC-IDRI-0566 excluded per §5.1. Geometry is approximate at this stage — in-plane offsets from
pixel indices × pixel spacing, z from `imageZposition`, contour volume from per-slice polygon area
× slice spacing with `inclusion=FALSE` subtracted; production uses the reconstructed mask.
Within-series relative distances are unaffected by the unknown patient-space origin.

**Total eligible pairs: 44,668.** **Radius-expanded-only pairs: 10** — admitted solely
because `r_i + r_j > 12 mm` *and* `12 mm < d(i,j) <= r_i + r_j` (§4.6.4).

| Pair type | Pairs | | Distance bin | Pairs |
|---|---:|---|---|---:|
| point-point | 34,350 | | [0,2) mm | 32,127 |
| contour-contour | 6,238 | | [2,4) | 4,795 |
| point-contour | 4,080 | | [4,6) | 2,130 |
| | | | [6,8) | 1,889 |
| | | | [8,10) | 1,854 |
| | | | [10,12] | 1,863 |
| | | | (12,∞) size-admitted | 10 |

| Category combination | Pairs | | Larger-mark size bin | Pairs |
|---|---:|---|---|---:|
| non_nodule + non_nodule | 20,900 | | n/a (point-only pair) | 34,350 |
| lt3 + lt3 | 10,703 | | <6 mm | 3,907 |
| ge3 + ge3 | 6,236 | | 6–10 mm | 3,935 |
| lt3 + non_nodule | 2,746 | | 10–20 mm | 1,970 |
| ge3 + lt3 | 2,473 | | ≥20 mm | 506 |
| ge3 + non_nodule | 1,610 | | | |

| Slice-thickness band | Pairs |
|---|---:|
| ≤1.25 mm | 19,507 |
| 1.25–2.5 mm | 19,745 |
| >2.5 mm | 5,416 |

**Near-miss band** (`2.0 mm <= d <= 10.0 mm`, §4.6.3): **10,672 pairs**, of which
**342 contour-contour**, 980 point-contour and 9,350 point-point.

**Pair type × distance band, full pool:**

| Pair type | [0,2) | [2,4) | [4,6) | [6,8) | [8,10) | [10,12] | (12,∞) | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| point-point | 23,406 | 4,024 | 1,953 | 1,725 | 1,644 | 1,598 | 0 | 34,350 |
| point-contour | 2,883 | 546 | 132 | 124 | 178 | 215 | 2 | 4,080 |
| contour-contour | 5,838 | 225 | 45 | 40 | 32 | 50 | 8 | 6,238 |
| **Total** | **32,127** | **4,795** | **2,130** | **1,889** | **1,854** | **1,863** | **10** | **44,668** |

The histogram bins above are half-open with a closed final `[10,12]` bin, whereas the near-miss
band is the **closed** interval `[2,10]` evaluated on `d` directly. The four pool pairs at
exactly `d = 10.0 mm` are therefore near-miss but appear in the `[10,12]` histogram bin
(4,795 + 2,130 + 1,889 + 1,854 = 10,668, and 10,672 − 10,668 = 4). The band definition, not the
histogram, governs sampling.

**Patients with ≥1 eligible pair, per sampling cell** — this is the availability that the
assignment in §4.6.3 must satisfy:

| Cell | Patients | Quota | Slack |
|---|---:|---:|---:|
| contour-contour \| near-miss | **129** | 90 | 39 |
| point-contour \| near-miss | 279 | 90 | 189 |
| point-contour \| other | 501 | 90 | 411 |
| contour-contour \| other | 649 | 90 | 559 |
| point-point \| near-miss | 663 | 120 | 543 |
| point-point \| other | 816 | 120 | 696 |

**Per patient:** 830 development patients have ≥1 eligible pair; median 41 pairs per such patient;
maximum 337.

**Grid-discriminating pairs.** A pair is *grid-discriminating* when the 15 proposed settings do
not all agree about it — the pairs that carry information about which setting to prefer. In the
full pool: **7,002 of 44,668 (15.7%)**. This is a geometric property of `(d, r_i, r_j)`; no
label, model output, or performance quantity is involved in computing it.

Two observations worth recording. The size term admits only **10** pairs, so it is numerically
negligible — but it is required for *correctness* of the precision denominator, because without it
a large-`α` setting could merge a pair the reference set never considered, silently inflating that
setting's measured precision. And **32,127 of 44,668 pairs sit below 2 mm**, so the pool is
dominated by near-coincident marks; the 2–10 mm near-miss band that actually discriminates between
grid settings is comparatively thin, which is why it is deliberately over-sampled.

#### 4.6.3 Joint sampling quotas — AMENDED at `0.2.1-draft`

**Exactly 600 primary pairwise decisions.** At `0.2.0-draft` the quota constrained pair type
alone (240/180/180) and near-miss enrichment was a 2× weight applied *within* each patient's
draw. That produced a manifest in which only **144 of 600 pairs (24%)** fell in the 2–10 mm
band — a weight, not a guarantee. **The weight is removed and replaced by an exact quota.**

**Near-miss is defined exactly as `2.0 mm <= d(i,j) <= 10.0 mm`**, inclusive at both ends.

The sampling strata are the **six joint cells** formed by pair type × near-miss band:

| Cell | Near-miss | Other | Pair-type total |
|---|---:|---:|---:|
| point-to-point | **120** | 120 | **240** |
| point-to-contour | **90** | 90 | **180** |
| contour-to-contour | **90** | 90 | **180** |
| **Total** | **300** | **300** | **600** |

Exactly **300 of 600** pairs are near-miss, allocated across pair types in proportion to the
pair-type quotas. Both marginals — 240/180/180 and 120/90/90 — are properties of a single
solution, not of three separate draws.

**This is a joint capacity-constrained matching problem and is solved as one.** Strata are
**never** generated independently and repaired afterwards: per-cell patient availability
overlaps heavily (§4.6.2), so independent draws would collide on the one-pair-per-patient rule,
and repairing collisions afterwards is an undocumented, order-dependent procedure with no
feasibility guarantee.

```
SRC        -> patient_i     capacity 1          exactly one primary pair per patient
patient_i  -> cell_g        capacity 1          iff the patient has >= 1 eligible pair in g
cell_g     -> SNK           capacity quota[g]   120 / 120 / 90 / 90 / 90 / 90
feasible   <=>  max flow == 600
```

All capacities are integers, so the maximum flow is integral and each unit of flow is exactly
one patient assigned to one cell. The solver is deterministic Dinic and **fails closed**.

- **Feasibility is proven before regeneration, not asserted.** On the hash-pinned corpus:
  830 eligible patients, 6 of them pinned by §4.6.4, **residual max flow 594 of 594 →
  600 of 600 assigned → feasible.** The binding cell is contour-contour near-miss, with 129
  eligible patients against a quota of 90.
- **If the exact joint quotas are ever infeasible, generation stops** and the report states the
  maximum achievable flow, the binding cells and their shortfalls, the patient conflicts
  (including patients eligible for only one cell), and the nearest feasible allocation.
  **Quotas are never silently relaxed**; changing one requires a new protocol version.
- **Exactly one primary pair per patient.** All 600 come from development patients.
- **The pair chosen within an assigned patient** is drawn uniformly at random, with a seed
  derived from the patient ID and the frozen sampling seed, **from that patient's pairs in the
  assigned cell only**. Because the cell already fixes the band, no additional near-miss
  weighting is applied — enriching twice, once by quota and once by weight, would produce an
  enrichment factor nobody declared.
- Determinism requirements: stable seeded priority derived from patient ID and the frozen
  sampling seed; no dependence on filesystem or XML input ordering; deterministic tie-breaking;
  an output manifest hash; and a permutation test showing that shuffled input produces
  byte-identical manifests across every round.
- **The patient IDs, sampling cells, seeds, and selected mark-pair IDs are frozen before any
  manual label is created.** The frozen selection is written once and hashed.
- **Every threshold setting is evaluated against all 600 primary labels.** There is **no**
  prefix cap, no first-*N* truncation, and no selection of an evaluation subset by candidate
  ordering. The entire eligible denominator is used; surplus predicted-positive pairs are
  never discarded.
- **Labels.** Three blinded options: same physical finding / different findings /
  **indeterminate**. Indeterminate pairs go to the blinded re-review; if still indeterminate
  they are excluded from threshold optimisation, their count is reported, and a sensitivity
  analysis assigns them both ways. **If more than 5% remain indeterminate, stop and revise the
  labelling rubric.**
- **Blinding.** The reviewer sees the two marks on the CT in three orthogonal views and each
  mark's geometric extent. The reviewer does **not** see mark categories, category agreement,
  session indices, the exact physical distance, any threshold setting, any vote distribution or
  entropy, or any model output.
- Stratification covers all three mark categories and cross-category pairs, contour size
  bands, slice-thickness bands, reader counts 3 and 4, and single- and multi-reader marks.
  Sampling and presentation-order seeds are recorded.
- Near-miss enrichment means measured precision is **pessimistic, not representative**. It is
  reported as *precision on an adversarially enriched reference set*, never as a population
  value; sampling weights are retained so a reweighted secondary estimate can be computed.
  The enrichment is now stronger and more precisely stated than at `0.2.0-draft`: the near-miss
  fraction is **0.500 by construction** against **0.239** in the eligible pool.

**Composition of the generated manifest**, all figures matching the quota exactly:

| Quantity | Value |
|---|---|
| Primary pairs / distinct patients | 600 / 600 |
| By pair type | 240 / 180 / 180 |
| By cell | 120 / 120 / 90 / 90 / 90 / 90 |
| Near-miss | **300 (0.500)**, as 120 / 90 / 90 |
| Grid-discriminating pairs | **255 of 600 (42.5%)**, against 15.7% in the pool |
| Radius-expanded-only pairs carried | 6 in primary + 4 in the census (§4.6.4) |

**Class-count shortfall rule.** If, after all 600 labels are complete, there are fewer than
**150 confirmed same-finding** or fewer than **150 confirmed different-finding** pairs, then:
the threshold grid is **not scored**; the shortfall is reported; and a **new protocol
amendment** defines a supplemental sample. The supplemental sample uses the original seeded
sampling logic and is **frozen before any threshold result is inspected**. Adaptive top-up and
scoring in the same undocumented step is prohibited.

#### 4.6.4 Radius-expanded-only pairs — mandatory coverage — AMENDED at `0.2.1-draft`

The pool contains exactly **10** pairs admitted *only* by the size term:

```
r_i + r_j > 12 mm        AND        12 mm < d(i,j) <= r_i + r_j
```

**All 10 must be represented in human review.** If any is unreviewed, the claim that the
size-expanded predicate prevents unscored large-`α` merges is false: an unreviewed pair that a
large-`α` setting merges is a merge the reference set cannot score, which silently inflates that
setting's precision. This is a correctness requirement, not a sampling preference.

Their diagnostic value is now measurable: of the 300 "other"-band pairs in the manifest, the
**only** grid-discriminating ones are the 6 radius-expanded-only pairs (4 contour-contour,
2 point-contour). Every other "other"-band pair is either merged by all 15 settings or by none.

**Exact feasibility result.** The 10 pairs come from **only 6 distinct development patients**:

| Pairs contributed by one patient | Patients | Placement |
|---:|---:|---|
| 3 | 1 | 1 primary, 2 census |
| 2 | 2 | 1 primary, 1 census each |
| 1 | 3 | primary |
| **10 pairs** | **6 patients** | **6 primary + 4 census** |

Because the primary set is **one pair per patient**, at most 6 of the 10 can enter it. This is a
patient conflict, not a stratum conflict: the cells they occupy (contour-contour other, quota 90;
point-contour other, quota 90) have ample capacity. **The maximum number of the 10 that any
600-pair, one-per-patient manifest can contain is therefore 6, and 6 is achieved.**

- **The 6 are pinned into the matching, not appended to it.** A pinned patient is removed from
  the sampled node set and its cell's quota decremented, so the residual problem (594 of 594) is
  solved exactly and the feasibility proof covers the pinned pairs. Every joint quota is still
  filled exactly.
- Where a patient carries several, the pinned one is the lowest `pair_id` — a SHA-256 digest of
  the two mark IDs, so the tie-break is deterministic, independent of geometry, and cannot be
  steered by any outcome.
- **No pair is discarded.** The remaining **4** go to a separate blinded
  `radius_expanded_census` manifest with its own opaque identifiers and presentation order.
  Pairs already in the primary 600 are deduplicated out, so **each of the 10 is reviewed exactly
  once** across the two manifests. A coverage audit asserts this and fails closed.
- **Census results are reported separately from the primary Wilson precision calculation.**
  The census is not one-pair-per-patient and is not a random sample, so folding it into the
  primary interval would violate §4.7 criterion 5 outright. **Census false merges are reported
  for every one of the 15 grid settings.**

##### Census veto rule — RATIFIED and FROZEN at `0.2.1-draft`, 2026-09-04

A supplemental census is necessary, so a veto rule is required. It was **predeclared and
ratified before any label existed**, and it is in force from this version.

> **Frozen.** A grid setting that produces **one or more confirmed false merges among the 4
> census pairs** is **rejected**, on the same zero-tolerance basis as the §4.7 cluster audit,
> regardless of its primary-set precision, its Wilson lower bound, or its rank. The veto is
> applied **after** the §4.7 eligibility and ranking computation and **before** the
> 100-candidate cluster audit, so it can only remove settings, never promote one. Census
> **false splits** are reported but never veto a setting, mirroring §4.7's asymmetric
> treatment of splits. Census pairs are **excluded** from the precision numerator and
> denominator, from the Wilson interval, and from the recall used for ranking. If every
> setting is vetoed, that is reported as a failure of the *formulation* and handled by §4.7's
> failure clause — the veto is never relaxed inside the same analysis.

Rationale for this form: these 4 pairs exist precisely because a large-`α` setting can
merge marks 13–23 mm apart. A setting that does so on a pair a human judges to be two distinct
findings is manufacturing reader agreement at exactly the scale the predicate was widened to
catch, and 4 observations are far too few to support a rate-based criterion — so the only
defensible rule is a zero-tolerance veto, not a threshold on a proportion.

#### 4.6.5 Ambiguous marks in the pool — RATIFIED at `0.2.1-draft`

The pool contains **2** pairs involving a mark categorised `ambiguous_unresolved`
(`label_schema.md` §3) — one `ambiguous + nodule_ge_3mm` and one
`ambiguous + non_nodule_ge_3mm`. **Both remain eligible for the association pool.**

Association is **category-agnostic** (§4.1, on Armato et al.'s own account of how LIDC grouped
marks across categories). Whether two marks are the same physical finding is a question about
geometry and imaging, and can be decided without knowing either category. Excluding a mark from
pairing *because* its category is unresolved would make association depend on category, which is
the one thing the pool predicate is built to avoid.

These marks remain **excluded from downstream benchmark labels**; eligibility for pairing and
membership of the label space are separate decisions. Neither pair was selected into the 600
(both belong to a single patient, which contributes at most one pair in any case), so no special
handling is required now. A regression test asserts that **category status cannot alter pool
eligibility, pair identity, or stratum** for any of the 16 category combinations.

#### 4.6.6 Reviewer governance — FROZEN at `0.2.1-draft`

**Terminology, binding on every public document.** The reference labels are a
**human-reviewed operational association reference**. They are **not** clinical ground truth.
The reviewer is **not** described as a radiologist, medical expert, or clinical annotator.

**Primary reference.**

- One named reviewer (the author) reviews **all 600** primary pairs.
- **Those labels alone** drive the predeclared threshold-selection calculation of §4.7.
- **No automated source may suggest, prefill, explain, or change a label.** There is no code
  path that derives a label from data; the store refuses any record from an unregistered
  reviewer, accepts only the three permitted values, and holds no free-text field.
- Exactly one reviewer may hold the primary-reference role; registering a second is refused.

**Intra-rater re-review.**

- Exactly **120** items, **preselected and frozen before any label exists**, stratified
  proportionally over the six joint cells (24/24/18/18/18/18, of which 60 are near-miss).
- Repeated after a **minimum seven-day washout**, enforced in code against the reviewer's last
  primary decision — an undefined washout counts as unsatisfied, so the round fails closed.
- **New opaque identifiers and an independently randomised order**, so a repeat item cannot be
  recognised or aligned with its primary counterpart.
- Hidden at re-review: the original decision, the exact physical distance, categories, vote
  distributions, downstream entropy, and all threshold-grid results.
- **Cohen's κ and raw agreement are reported. κ ≥ 0.80 is required.** On failure the rubric is
  refined and the pilot repeats on a **newly sampled** subset.
- **Repeated answers never overwrite original answers.** Rounds are stored separately and the
  store is append-only.

**Independent review.**

- The tooling **must** support a second reviewer on the **same 120-item subset**, with its own
  opaque identifiers and its own randomised order. This is implemented and tested.
- It is **strongly recommended** if an adviser or other competent reviewer is available.
- It is treated as an **external reproducibility audit**. It does **not** replace or adjudicate
  the primary labels, and it does **not** change the selected threshold. The store refuses to
  let an independent reviewer write the `primary` or `radius_expanded_census` rounds at all.
- Availability is **not a hard blocker**. If no second reviewer is available, the
  single-reviewer association assessment is recorded as a **stated study limitation**, in the
  limitations section and in the manuscript.

### 4.7 Selection rule — frozen

**Eligibility.** A setting is eligible only if **all five** hold:

1. **observed association precision ≥ 0.990**;
2. **95% Wilson lower confidence bound on precision ≥ 0.950**;
3. at least **150 predicted-positive pairs**;
4. every structural invariant in §4.4 passes;
5. all labels used by the primary interval are **patient-independent**.

The two precision criteria do different jobs and both are required. The Wilson bound alone is
a *confidence* requirement: the observed proportion needed to clear it falls as the sample
grows, because more data give greater certainty — at 150 predicted positives it implies ≈98.7%
observed, at 400 only ≈97.3%. Criterion 1 adds a **fixed substantive limit on manufactured
agreement**, making the observed false-merge tolerance independent of sample size. Criterion 2
ensures that limit is not met by luck on a small sample.

If criterion 5 is ever violated — more than one scored pair from a patient — the ordinary
Wilson interval is replaced by a **patient-clustered bootstrap** interval, and any additional
same-patient pairs are retained only as diagnostic examples, never as independent observations.

**The §4.6.4 census is outside all five criteria.** Its 4 pairs are not one-per-patient and are
not a random sample; they enter neither the precision numerator, the denominator, the Wilson
interval, nor the recall used for ranking. They are reported separately for all 15 settings,
and under the frozen §4.6.4 veto rule may **reject** a setting but never promote one.

**Ranking among eligible settings**, in strict order:
1. highest recall;
2. then highest precision lower bound;
3. then smaller `τ_floor`;
4. then smaller `α`.

**Cluster-level audit.** Pairwise accuracy does not prove that complete-linkage clustering
behaves correctly at the candidate level. The top-ranked setting must then pass an independent
audit of **100 candidate clusters**:

- drawn from development patients **not represented in the 600-pair reference set**;
- **one audited candidate per patient**;
- candidate IDs **frozen and hashed before any threshold-grid result is revealed**;
- **50 randomly sampled** + **50 adversarial**, the latter covering nearby findings, mixed
  categories, large lesions, point-to-contour matches, and threshold-boundary cases;
- **no locked-test patients**;
- **no model predictions and no disagreement outcomes used to select audit cases**;
- **zero confirmed false merges permitted.**

If a false merge is confirmed, that setting is **rejected** and the next eligible setting is
audited. False splits are reported and handled through recall and sensitivity analysis, never
by relaxing the false-merge rule. If fewer than 100 eligible unused patients remain, **stop and
amend the audit** — pair-reference patients are never silently reused; the exact shortage is
reported and a patient-clustered alternative proposed **before** proceeding.

**Development-patient reconciliation (verified 2026-08-31), summing exactly:**

| Group | Patients |
|---|---|
| Development patients | **833** |
| − with no marks at all: LIDC-IDRI-0566 | 1 |
| − with marks but no eligible cross-session pair: LIDC-IDRI-0668, LIDC-IDRI-0693 | 2 |
| = eligible for pair sampling | **830** |
| − consumed by the 600-pair reference set | 600 |
| = pair-eligible patients remaining | **230** |
| + patients with marks but no eligible pair (still yield single-mark candidates) | 2 |
| **= patients available for the cluster audit** | **232** |

Check: 1 + 2 + 830 = 833 ✓.  232 ≥ 100 → the audit population is available with 2.3× headroom.

The §4.6.4 census consumes **no additional patients**: all 4 census pairs belong to three
patients that already contribute a primary pair. The audit population is therefore unchanged
at 232.

LIDC-IDRI-0566 shows zero marks here **because its only series is the excluded eight-session
panel** (§5.1) — not because the subject is unannotated. That distinction matters: it is a
consequence of our own exclusion rule, and it is the reason 832 rather than 833 patients have
usable marks.

**Failure.** If no setting passes, the failure is reported and the association *formulation* is
revised in a **new protocol version**. Criteria are never relaxed inside the same analysis.

**What must never drive selection:** model accuracy, uncertainty correlation, reader-vote
entropy, class balance, or final dataset size. None is computed, or computable, before the
threshold is fixed.

**Sensitivity analysis.** The selected setting ±1 grid step in each direction is carried into
the final report: candidate count, vote-distribution shift, and the primary Spearman
statistic under each. If the primary conclusion flips within one grid step, that fragility is
a headline limitation.

Internal artefacts — reference labels, selection code — are not published. A human-facing
summary of the frozen procedure appears in this document at `0.3.0`.

### 4.8 Retired from the benchmark

The prototype's randomly sampled image crops are **removed from the primary benchmark**. Their
sampling was never constrained by a lung mask, so they are not a valid lung-tissue control and
are **not** relabelled as one. Any future easy-negative control must be rebuilt from scratch
with an explicit lung mask and named explicitly as an easy control.

This costs nothing: the annotation XML contains 21,663 radiologist-marked `non_nodule_ge_3mm`
marks — genuine reader-identified look-alikes — which the study uses instead.

---

## 5. Reader panels and partitions

### 5.1 Reader panels

The reading-session count is **per scan** and is never hardcoded.

- The 1,016 four-session scans are included with denominator 4.
- The single three-session scan (**LIDC-IDRI-0700**) is included with **denominator 3**.
- The single eight-session series (**LIDC-IDRI-0566**) is **excluded from the primary study**:
  it contains two four-reader panels that cannot currently be separated with sufficient
  confidence. The exclusion is recorded **before** candidate construction and reported in the
  cohort flow.
- A panel-splitting sensitivity analysis is permitted later **only** if a deterministic,
  independently verifiable grouping rule is found. **Document ordering alone must not be used**
  — the apparent 0–3 / 4–7 structure is suggestive, not evidence.

### 5.2 Partitions

- Splitting is **by patient**, never by scan or candidate.
- **Partition proportions and justification.** 177 locked-test patients of 1,010 (**17.5%**) with
  the remaining 833 in five development folds. The holdout fraction was chosen to leave a test set
  large enough for patient-clustered intervals on the primary statistic while keeping ~82% of
  patients available for five-fold development; it was fixed before any modelling and has not been
  revisited. This satisfies CLAIM's requirement to "specify how the data were assigned into
  training, validation ("tuning"), and testing partitions; indicate the proportion of data in each
  partition and justify that selection".
- **Level of disjointness: patient.** CLAIM states that "sets of medical images generally should be
  disjoint at the patient level or higher so that images of the same patient do not appear in each
  partition" — an external requirement this project already meets, not a preference of ours.
- The **locked test set is fixed at 177 patients** and its membership does not change.
  SHA-256 of the sorted, newline-joined patient-ID list:
  `35fdf2b93ee883cf3633e2656d224df6376db9687f434760dc1df8d05e0c0983`.
  This hash is asserted in code before any split is written and before any final evaluation.
- The five development folds over the remaining 833 patients are regenerated **once**, to
  stratify the new candidate/vote target. Regeneration must leave the test hash unchanged.
- Calibration folds are patient-disjoint.
- Tests enforce: no patient in two splits, and every candidate resolving to a manifest patient.

---

## 6. Models

All primary models emit **four logits** and are trained against the empirical vote
distribution with distributional cross-entropy, $L_i = -\sum_k y_{ik} \log q_{ik}$.

| ID | Model | Purpose |
|---|---|---|
| B0 | Frequency / simple metadata | Non-image performance floor. **May involve fitted fold-specific baselines** (e.g. per-fold class frequencies or a metadata regression) and so counts as 5 runs, but its compute cost is **not comparable to neural-network training** and must not be presented as if it were. |
| B1 | Deterministic axial ResNet-18 | Minimal 2D baseline |
| B2 | Deterministic three-view shared ResNet-18 | Tests the multi-view design |
| U1 | Three-view MC-dropout ResNet-18 | Approximate-Bayesian uncertainty baseline |
| U2 | Five-member deep ensemble | Strong uncertainty baseline |
| V1 | Compact 3D CNN | Tests information lost by central slices |

**Fair comparison.** Identical patient folds, candidate definitions, physical field of view,
normalisation, augmentation policy, early-stopping rule, and metric code. Matched optimisation
effort. Parameter count, training time, peak memory, and inference time recorded per run.

**Augmentation.** Geometric augmentations are sampled **once per candidate and applied
identically to all views**. Independently augmenting the three orthogonal views of one lesion
destroys their geometric relationship and is prohibited. Intensity jitter is not applied to
HU-windowed data by default.

**Determinism.** Ordinary evaluation must be deterministic; stochastic inference occurs only
where explicitly requested. Enforced by test: two `eval()` forward passes on identical input
must agree. Early stopping and model selection use deterministic validation passes only.

Seeds are set for Python, NumPy, and PyTorch; unavoidable MPS nondeterminism is documented. At
least three training seeds are used for stochastic comparisons where compute allows; if not,
the limitation is stated and fixed-prediction bootstrap is **not** described as capturing
training variance.

**No training may begin before the timing/memory benchmark and compute plan are approved.**

---

## 7. Uncertainty and calibration

Computed and reported **separately**, each defined operationally: predictive entropy of the
mean probability; expected entropy across passes or members; mutual information; per-class
predictive variance; one-minus-max-probability; and ensemble member disagreement.

Mutual information is reported as a *candidate* epistemic score. This project does not claim
that entropy minus expected entropy is a guaranteed causal decomposition of aleatoric and
epistemic uncertainty.

**MC-dropout sampling and convergence.** For each prediction set and each checkpoint,
**100 stochastic passes are produced once**, with sufficient summary data stored or streamed
reproducibly. Convergence at 6, 20, 50 and 100 is then evaluated on **nested prefixes of those
same stored passes** — the first 6, the first 20, the first 50, all 100.

- **Four independent inference jobs are not run.** Prefixes of one ordered sample are nested by
  construction, so the convergence curve is monotone in evidence rather than confounded by
  between-job sampling noise, and the 6-pass estimate is literally a subsample of the 100-pass
  estimate — which is what makes "has it converged?" well-posed.
- **The prefixes are not counted as separate inference runs**, and this must not be described as
  "60 passes" or any similar figure that multiplies checkpoints by prefix counts.
- **Pass ordering and the inference seed are recorded**, since the prefix result depends on order.
- 50 remains the default only if convergence supports it.

The ensemble uses five independently initialised members with recorded seeds.

**Calibration is cross-fitted.** Patient-disjoint out-of-fold logits are produced for every
development candidate; those are split by patient into calibration folds; temperature is fit on
the complement of each fold and evaluated on the held-out fold; the final temperature is fit on
all development OOF logits and applied **once** to locked-test logits. Uncalibrated results are
always preserved alongside calibrated ones.

No fixed temperature is used anywhere in the scientific pipeline. All prototype calibration
results produced with a fixed, unfitted temperature are void and are not cited as evidence.

---

## 8. Outcomes — PREDECLARED

### Primary

**Primary disagreement variable:** normalised entropy of the empirical four-category
reader-vote distribution.

**Primary uncertainty score:** **predictive entropy of the mean four-category predicted
distribution.** The *same* operational definition is used for deterministic, MC-dropout, and
ensemble models, so the methods remain comparable.

**Primary statistical analysis:** Spearman correlation between the two; patient-clustered
bootstrap 95% confidence interval; patient-level permutation test.

> **The primary uncertainty score is predeclared, not selected.** Earlier drafts said it would
> be "selected using development results and frozen." Choosing the best-performing estimator
> is a garden-of-forking-paths risk even with the test set sealed. Predeclaration is strictly
> stronger and is now binding.

### Secondary

**Secondary uncertainty quantities**, all remaining secondary: expected entropy; mutual
information; per-class predictive variance; ensemble-member disagreement;
one-minus-maximum probability.

**High-disagreement secondary outcome:** `max(empirical vote distribution) ≤ 0.5` — no
category holds a strict reader majority.

**Secondary hard ≥3 mm label:** `nodule_ge_3mm` vote fraction **> 0.5**. Exact ties are
**excluded** from thresholded classification metrics but **retained** in all distributional and
disagreement analyses. The soft target is the `nodule_ge_3mm` vote fraction itself.

Interaction to report explicitly: at denominator 4, a 2–2 split is simultaneously
"high disagreement" and an excluded tie in the derived analysis; at denominator 3 no exact 0.5
is reachable. Counts for both appear in the cohort flow.

**Secondary hypotheses.** H2 ensemble beats single deterministic and MC dropout on
disagreement detection and risk-coverage; H3 three-view beats axial-only on
distribution-prediction quality; H4 compact 3D improves at least one predeclared predictive
metric over three-view; H5 uncertainty-based referral beats random referral. Confirmatory
secondary p-values are Holm-corrected. Any analysis not listed here is labelled exploratory.

### Metrics

**Distribution prediction (primary):** distributional NLL, multiclass Brier,
Jensen-Shannon divergence between predicted and empirical vote distributions.

**Derived-label (secondary) — PREDECLARED.** The AUROC/AUPRC target is:

- **positive class:** candidates with a **strict majority** for `nodule_ge_3mm`
  (vote fraction > 0.5);
- **negative class:** **all non-tied alternatives** — candidates whose `nodule_ge_3mm` vote
  fraction is < 0.5;
- **excluded:** exact ties (`= 0.5`), which are excluded from every thresholded metric but
  **retained** in all distributional, calibration, uncertainty and disagreement analyses;
- **candidate-level score:** the model's **predicted probability for `nodule_ge_3mm`**;
- **intervals:** patient-clustered bootstrap;
- **status: explicitly secondary.** Not the primary outcome, and never used for model selection.

Also reported: balanced accuracy, sensitivity, specificity at a development-selected threshold, and
macro/per-class metrics where counts permit. Accuracy is never reported without class counts.

**Disagreement detection:** the primary Spearman statistic; AUROC/AUPRC for the
high-disagreement group; calibration of predicted probabilities against empirical vote
distributions. Threshold-free analyses accompany any thresholded one.

**Referral / risk-coverage — PREDECLARED:**
- the **full risk-coverage curve** is reported;
- risk is reported at coverage **90%, 80%, 70%, and 50%**;
- risks used are **retained-candidate NLL** and **retained-candidate Brier score** (both);
- **AURC** is reported;
- compared against **random referral** and **one-minus-maximum-probability**.

**Calibration:** NLL and Brier before and after calibration, classwise or adaptive ECE with bin
counts and intervals, reliability diagrams, calibration slope and intercept. ECE alone is never
presented as proof of calibration.

The **binning scheme and bin count are declared explicitly** with every ECE figure. Guo et al.
2017 define `ECE = SUM_m (|B_m|/n) * |acc(B_m) - conf(B_m)|` over equally-spaced bins, use
`M = 15`, and note that reliability diagrams "do not display the proportion of samples in a given
bin". Reporting bin populations alongside every diagram is therefore a requirement, not a
courtesy.

That paper's supplementary Table S1 caption additionally reports that "MCE seems very sensitive
to the binning scheme and is less suited for small test sets". **That sentence is about maximum
calibration error, not ECE**, and is recorded here at its original scope. Binning sensitivity is
treated as a general caution of ours about binned calibration summaries — it is not attributed to
Guo et al. as a finding about ECE.

**FROC is not reported.** This is a candidate-classification study with no per-scan candidate
generator, so no false-positive-per-scan rate is defined. Prototype FROC values are withdrawn
entirely, not caveated.

---

## 9. Statistical procedure — PREDECLARED

Resampling is over **patients**, not candidates.

| Constant | Value |
|---|---|
| Patient-clustered bootstrap replicates | **2,000** |
| Patient-level permutation replicates | **10,000** |
| Analysis seed | **one fixed, recorded value**, declared in the run registry |

**Paired methods must use identical bootstrap samples and identical permutations.** The
resampling indices are generated once from the fixed analysis seed and reused across every
method being compared, so paired differences are not inflated by independent resampling noise.

Effect sizes and intervals are reported, not only p-values. Holm correction applies to
confirmatory secondary comparisons. Underpowered subgroups are labelled exploratory.

---

## 10. Subgroups and robustness

Audited by physical candidate diameter; solid/subsolid appearance where defined; reader count;
agreement level; slice thickness and reconstructed spacing; manufacturer; reconstruction kernel
family; and source mark category. Counts and intervals reported for every subgroup.
Preprocessing perturbations are limited to those within LIDC's own support.

**Spiculation and lobulation are excluded as confirmatory subgroup variables** (erratum 1:
inconsistent rating systems across five sites in ~100 of the initial 399 cases). They may appear
**only** in an explicitly exploratory sensitivity analysis that:

- excludes affected cases by a documented rule;
- reports the reduced sample size;
- does not affect the primary outcome;
- does not influence model or threshold selection.

Using a variable whose scale differs by contributing site as a confirmatory subgroup would produce
a difference attributable to acquisition site rather than to lesion appearance.

**`internalStructure == 5` is represented as invalid/missing and never coerced into a valid
category** (erratum 7; confirmed present once in `187/255.xml`, LIDC-IDRI-0510). Coercing it to the
nearest valid value would fabricate a reader judgement that was never recorded.

---

## 11. Explanations

Saliency claims are limited to measured mask overlap and failure analysis. Grad-CAM is a
debugging tool and is never presented as evidence of radiologist-like reasoning.

Required: saliency mapped back to each view's physical/mask coordinates; pointing-game success;
fraction of positive saliency energy inside union, intersection, and consensus masks; comparison
across agreement levels; and **model-parameter and label-randomisation sanity checks**.

**Two constraints follow from Adebayo et al. 2018, verified at source:**

1. **Guided Grad-CAM and Guided BackProp must not be used.** The paper reports that "Guided
   Backprop (along with Guided GradCAM) is invariant to higher layer weights" — they fail the very
   randomisation tests mandated here. Plain Grad-CAM is used, which the paper reports **passes**
   both tests.
2. **The parameter-randomisation control must randomise layers downstream of the target layer.**
   The paper's finding is that "GradCAM is sensitive to model weights if the randomization is
   downstream of the last convolutional layer." Because this project targets `layer2` (the final
   convolutional block collapses to 2x2 at 64x64 input), the control randomises layers downstream
   of `layer2`. Randomising upstream layers would not be a valid instance of the test.

Distance from a crop centre is not an acceptable localisation metric here, because candidates
are centred by construction, which makes the measure circular.

---

## 12. Locked-test procedure

The locked test set is not accessed — not evaluated, summarised, visualised, calibrated on, or
used for model selection — until every precondition below holds.

**Preconditions.** Clean working tree; this protocol frozen at `1.0.0` and committed; the test
membership hash matching; the final model list, seeds, calibration objects, metrics, and
subgroup definitions committed; the primary uncertainty score committed (already predeclared,
§8); and explicit authorisation from the author.

**Procedure.** Record the intended access before execution; run **one** final-test command; save
raw logits, member predictions, calibrated probabilities, uncertainty measures, and metadata;
generate the predeclared report automatically; record the outcome and checksums.

**No post-test tuning.** The model and protocol are not changed in response to the result. If a
software defect invalidates a run, it is documented in the access log, fixed without inspecting
further outcomes, and any rerun is classified transparently in all reports.

A private access log records every access; a concise summary appears in the public release. As
of this draft, **the locked test set has never been accessed.**

---

## 13. Reporting

Every report distinguishes: development OOF from locked-test results; candidate classification
from scan-level detection; reader-perceived categories from pathology-confirmed diagnoses;
empirical reader disagreement from model epistemic uncertainty; statistical uncertainty from
training-run variability; planned from exploratory analyses; and a retrospective public-dataset
study from a clinical device.

**CLAIM** (Mongan J, Moy L, Kahn CE Jr. *Checklist for Artificial Intelligence in Medical Imaging
(CLAIM): A Guide for Authors and Reviewers.* Radiol Artif Intell 2020;2(2):e200029) is the
manuscript reporting checklist. It also requires describing "the method and performance parameters
used to select the best-performing model among all the models trained for evaluation against the
held-out test set", which §8 and §12 address. A 2024 update to CLAIM exists and is the edition to
follow at manuscript stage; its item numbering is **not** relied on here because that edition has
not yet been read at full text. All protocol deviations are reported.

Prototype results produced before this protocol are **legacy** and are not used for model
selection, calibration claims, or publication evidence. Where prototype history is described,
its known defects are stated with it.

---

## 14. Success criteria

The study succeeds if the benchmark is valid, reproducible, and honestly reported — **including
if every hypothesis is unsupported.** A well-powered null result is a legitimate outcome and
will be reported as such.

Near-perfect classification accuracy is **not** a success criterion. High accuracy on this
benchmark would more likely indicate that the task has become too easy than that the method is
good.

---

## 15. Gate status and remaining work

### A. Documentation gate — **PASS**

Every source cited in this document has been verified at **full text** or is **authoritative
primary documentation**. An abstract alone is not accepted, and no public claim rests on one.
`0.2.1-draft` cites no new source.

**The phrase-overlap and attribution audit was rebuilt and rerun in full at `0.2.1-draft`.** The
complete text of all 17 cited sources was re-obtained from its canonical lawful location, and
**both complete public documents** — not merely the amended sections — were checked by exact
10-word n-gram matching against that corpus. Every detected run was inspected in context. Two
quotations were corrected as a result (see the table below). After the corrections the audit is
clean: every remaining overlap is a quoted-and-attributed passage, a bibliographic entry, a
standard equation, or the licence-mandated dataset citation, and **no unattributed prose overlap
remains.**

Verified at full text this session: Gal & Ghahramani 2016 (ICML/PMLR v48); Lakshminarayanan et al.
2017 (NIPS); Selvaraju et al. 2017 (ICCV); He et al. 2016 (CVPR); Setio et al. 2016 (IEEE TMI
35(5):1160–1169); Ovadia et al. 2019 (NeurIPS); CLAIM (Mongan et al., Radiol Artif Intell
2020;2(2):e200029, via PubMed Central). Previously verified: Armato et al. 2011, Guo et al. 2017,
Kendall & Gal 2017, Adebayo et al. 2018, Liao et al. 2021, Zahari et al. 2024, plus four primary
documentation sources (TCIA collection page, LUNA16 evaluation page, two pylidc API pages).

**Claims narrowed or corrected as a direct result of full-text reading** — recorded here because
each was a public statement that the source did not support as written:

| Was stated | Corrected to |
|---|---|
| The five-member ensemble size is our own convention, not prescribed by Lakshminarayanan et al. | **Wrong.** That paper's Algorithm 1 states "Recommended default values are M = 5". Our M = 5 follows the paper, and Ovadia et al. independently report M = 5 may suffice. |
| ResNet-18 is not named in He et al., so the specific variant cannot be cited to it | **Wrong.** The 18-layer residual variant is evaluated there (Table 1, Table 2, Fig. 4). The backbone is attributable. |
| Our three-view design is "a simplification" of Setio et al. | **Understated.** Setio et al. evaluate 1-, 3- and 9-view configurations with 50 × 50 mm patches at 64 × 64 px. Our three-view model is one of the configurations they already tested, and fixed-physical-patch extraction is their convention. |
| Ovadia et al. show "post-hoc calibration falls short" (generic) | **Sharpened.** They benchmark temperature scaling by name and find most other methods beat it on Brier score under shift, with ECE rising as shift grows. |
| CLAIM 2024 Items 19 / 20 / 22 require partition proportions, patient-level disjointness, model-selection reporting | **Item numbering removed.** The requirements are quoted from CLAIM **2020**, read at full text. The 2024 update was never read; its numbering is no longer cited. |
| Grad-CAM is computed at a target layer of our choosing | **Qualified.** Selvaraju et al. compute it at the *last* convolutional layer and justify that as "the best compromise between high-level semantics and detailed spatial information". Our earlier-layer use is a documented deviation. |
| Guo et al. described as calling "such measures" — in a passage about ECE — "very sensitive to the binning scheme and less suited for small test sets" | **Wrong on scope and on wording.** The sentence is from that paper's supplementary Table S1 caption, reads "MCE seems very sensitive to the binning scheme and is less suited for small test sets", and is about **maximum** calibration error, not ECE. It is now quoted exactly and at its original scope; binning sensitivity is stated as a caution of ours, not as a Guo et al. finding about ECE. Found by the `0.2.1-draft` audit rerun. |
| The 2018-06-28 TCIA erratum quoted in `label_schema.md` as "One reader recorded a nodule ≥3 mm but omitted characteristic ratings; files updated with error explanation" | **A paraphrase presented as a quotation.** TCIA's wording is "neglected to assign ratings for the nodule characteristics", and that "the files were updated with an explanation at the point of the error in the XML files". Both are now quoted exactly. The claim built on it — that TCIA documented the omission rather than supplying the ratings — is unchanged and is still supported. Found by the `0.2.1-draft` audit rerun. |
| C-UQ 2025 cited as adjacent prior art | **Citation removed** from this document. No lawful full text is available (publisher 403; no repository copy in OpenAIRE), so it cannot be compared methodologically. It is retained privately as abstract-only and is **not** replaced by any novelty claim. |

Two previously-relied-upon claims remain **withdrawn for want of any source**; neither ever
appeared in a public document, and no experiment has been interpreted using either.

### B. Gate 2 — association freeze (OPEN)

1. Execute the §4.6 pilot on the frozen 600-pair reference set, plus the 4-pair census.
2. Pass the §4.7 100-candidate cluster audit with zero confirmed false merges.
3. Record the selected setting and the sensitivity analysis in a `0.3.0` revision.

Until all three are done, **no association threshold is frozen** and no candidate dataset may be
built.

**Done at `0.2.1-draft`, before any label exists:** manifests generated, blinded and hashed;
joint feasibility proven at 600/600; all 10 radius-expanded-only pairs placed; the repeat,
independent and census rounds built; 20 shuffled-input rebuilds byte-identical across all five
artifacts; blinding audit passing on all four reviewer-facing manifests.

**Not done, and not permitted before the items above:** creating any reference label, opening
the review interface on real cases for labelling, computing any threshold performance,
selecting a threshold, or running the cluster audit. **Zero reference labels exist.**

### C. Gate 3 — preprocessing / field-of-view freeze (OPEN)

1. Construct candidates using the declared §3.5 specification.
2. Run the **development-only** truncation audit: ≥99% of contour candidates retaining the complete
   union mask plus a 5 mm margin.
3. If the rule fails, amend to a larger fixed physical field of view **before training** — never by
   excluding large candidates — then rerun preprocessing validation.
4. Freeze the field of view in a later revision.

### D. Other work before `1.0.0`

- Compute-plan approval and the post-dataset timing/memory benchmark (§6). **No training is
  authorised until the candidate benchmark is frozen, the measured benchmark is complete, the
  compute plan is updated, and the author approves the final budget.**
- Re-verify the CLAIM 2024 update at full text before manuscript submission (§13).

### E. Resolved since `0.1.0-draft`

Corpus hash-pinned and confirmed current; all eight errata verified and handled; supersession
resolved on official authority; payload-level duplicate canonicalisation; category reconciliation
passing a fail-closed gate; reader panels frozen; entropy convention, high-disagreement label, derived hard label, **derived
AUROC/AUPRC target**, risk-coverage levels and statistical replicates all predeclared; pilot
reference set fixed at 600 with a dual precision criterion, an exact pool predicate, and an exact
capacity-constrained matching with a proven-feasible assignment; duplicate-timepoint handling
frozen; primary preprocessing **declared** (its field of view awaits gate 3).

### F. Resolved at `0.2.1-draft`

Counting scopes stated explicitly and reconciled; near-miss enrichment converted from a weight
to an exact **300/600** quota with per-pair-type allocation; sampling reformulated as a single
**joint** capacity-constrained matching, feasibility proven at 600/600 before regeneration;
all **10** radius-expanded-only pairs placed into review with a fail-closed coverage audit;
ambiguous-mark pool eligibility ratified with a regression test; reviewer governance frozen and
enforced in code; the §4.6.4 census veto rule ratified and frozen **before any label existed**;
the 17-source corpus rebuilt and the phrase-overlap/attribution audit rerun over both complete
documents, with two inexact quotations corrected (§15.A). **Nothing is open at this revision
beyond gates 2 and 3 themselves.**

### Note on prior art and novelty

Two withdrawn claims and one close prior work require the contribution statement in §2 to stay
narrow:

- A previously-relied-upon "null result on uncertainty versus expert disagreement" in an
  adjacent domain **could not be substantiated** and has been withdrawn. No experiment in this
  project has been interpreted using it.
- A previously-relied-upon "per-characteristic reader-disagreement ordering" **could not be
  substantiated**, and the direction of the one available related finding appears opposite to
  what was assumed. Withdrawn; not inverted and re-adopted, because the inverse is equally
  unverified.
- **Zahari, Cox & Obara, *Uncertainty-aware image classification on 3D CT lung*, Computers in
  Biology and Medicine 172 (2024)** compares MC dropout, deep ensembles, and ensemble MC
  dropout on 3D CT lung-nodule classification with a referral analysis. That overlaps
  substantially with this project's U1/U2 comparison and H5. Whether it also relates
  uncertainty to reader disagreement is **not yet established** and must be settled before any
  novelty claim is made. On present evidence this project's distinguishing element is the
  four-category reader-vote target and the disagreement association — **not** the
  uncertainty-method comparison or the referral analysis, both of which should be presented as
  replication in a new label setting rather than as new contributions.

## Amendments

| Version | Date | Change |
|---|---|---|
| `0.2.1-draft` | 2026-09-04 | **Scopes.** Stated the two counting scopes explicitly and side by side (§3.2): corpus/parser reconciliation over **all 1,018 CT series and all 41,759 marks**, and primary analysis over **1,017 series and 41,675 marks** with LIDC-IDRI-0566 and its 84 marks removed. The eight-session exclusion is recorded as an **analysis decision, not a parser rule**; corpus counts are not replaced by primary counts anywhere. **Near-miss enrichment.** Rejected the `0.2.0-draft` manifest, in which only **144 of 600 pairs (24%)** fell in the intended band, because near-miss was a 2× within-patient weight rather than a quota. Defined near-miss exactly as `2.0 mm <= d <= 10.0 mm` and required **exactly 300 of 600**, allocated proportionally as **120 point-point / 90 point-contour / 90 contour-contour** (§4.6.3). Reformulated sampling as a **single joint capacity-constrained matching over six pair-type × band cells**, solved by integral max flow and **proven feasible before regeneration** (600/600); strata are never drawn independently and repaired, and infeasibility stops generation with maximum achievable flow, binding cells, patient conflicts and the nearest feasible allocation. Removed the redundant within-patient near-miss weight. Amended **before any label existed**, so no outcome could have informed it. **Radius-expanded-only pairs** (§4.6.4): defined exactly as `r_i + r_j > 12` and `12 < d <= r_i + r_j`; established that the 10 come from only **6 distinct patients**, so **6 is the maximum any one-pair-per-patient manifest can hold**; pinned those 6 into the matching itself; sent the other **4** to a separate blinded `radius_expanded_census` manifest, deduplicated, with a fail-closed coverage audit proving each of the 10 is reviewed exactly once. Census results are kept out of the primary Wilson calculation and reported for all 15 settings. **Ratified and froze the census veto rule** — one or more confirmed census false merges rejects a setting, applied after §4.7 ranking and before the cluster audit, splits reported but never vetoing — **predeclared before any label existed**. Replaced the six named development patient IDs in the radius-expanded conflict table with counts, which carries the same evidential force without disclosing development-set membership. **Ambiguous marks** (§4.6.5): ratified as **eligible** for the association pool, since association is category-agnostic and excluding them would make it depend on category; they remain excluded from downstream benchmark labels, and a regression test asserts category cannot alter eligibility, pair identity, or stratum. **Reviewer governance** frozen (§4.6.6): one primary-reference reviewer over all 600; code-enforced seven-day washout for the 120-item intra-rater round with new identifiers and independent order; κ ≥ 0.80; a supported independent second reviewer on the same 120 items as an external audit that cannot adjudicate or change the threshold, with single-reviewer assessment recorded as a limitation if unavailable; and the binding terminology **"human-reviewed operational association reference"**, never "clinical ground truth" and never "radiologist". **Documentation gate rerun.** The 17-source full-text corpus was rebuilt from canonical lawful locations and the phrase-overlap/attribution audit rerun over **both complete documents**. Two quotations were corrected: a Guo et al. sentence had been quoted inexactly *and* generalised from MCE to ECE, and a TCIA erratum paraphrase had been presented inside quotation marks. Both are now exact and correctly scoped; neither claim they support changed. Zero unattributed prose overlap remains. Thresholds remain **proposed, not frozen**; **zero reference labels exist**. |
| `0.1.0-draft` | 2026-08-30 | Initial draft, written from a direct survey of the original LIDC annotation XML. Committed as `6bd0f6b` to timestamp the protocol before any threshold was chosen. |
| `0.2.0-draft` | 2026-08-31 (rev. b) | Hash-pinned the annotation corpus (SHA-256 `644557a3…`, accessed 2026-08-31) and **withdrew the earlier "stale corpus" claim** — the current official archive is byte-identical to the copy already held; TCIA documented the missing-ratings omission rather than supplying the ratings, so it is permanent. Documented all **eight** errata (four newly found: site-inconsistent spiculation/lobulation, non-persistent reader order, invalid `internalStructure=5`, eight duplicate-timepoint patients). Corrected duplicate-file canonicalisation to **payload level**, which resolves four apparent content differences as cosmetic and leaves exactly one genuine case (resolved by erratum). Fixed the pilot reference set at **600 pairs** (240/180/180) with one pair per patient, all 600 scored for every setting, **no prefix cap**; added the class-count shortfall rule requiring a new protocol amendment rather than adaptive top-up. Added the **dual precision criterion** (observed ≥ 0.990 **and** Wilson 95% LB ≥ 0.950) so false-merge tolerance no longer varies with sample size. Made the 100-cluster audit use patients disjoint from the pair sample, one candidate per patient. Predeclared risk-coverage levels (90/80/70/50%), bootstrap (2,000) and permutation (10,000) replicates with a fixed shared seed, and the nested-prefix MC-dropout convergence scheme. Recorded prior-art and withdrawn-claim status. | 
| `0.2.0-draft` | 2026-08-31 (rev. a) | Added TCIA DOI, licence, citation, and the four official errata, including the finding that the local corpus **predates the 2018-06-28 corrections** and must be re-downloaded. Resolved LIDC-IDRI-0101 supersession on the authority of TCIA's correction notice. Predeclared the primary uncertainty score, high-disagreement outcome, and derived hard label (§8), superseding the earlier "select on development data" language. Added full reproducible geometry definitions, constrained agglomerative complete linkage, zero-tolerance structural invariants, the frozen selection rule with a ≥150 predicted-positive floor and the 100-cluster audit, and the pilot's independence, indeterminate-label, and intra-rater (κ ≥ 0.80, 20% re-review) requirements (§4). Recorded reader-panel decisions with subject IDs (§5.1). Added closest-prior-art positioning (§2). Association thresholds remain **proposed, not frozen**. |
