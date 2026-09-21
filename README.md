# LIDC Reader Disagreement

A retrospective, single-dataset methodological study on the public **LIDC-IDRI** CT collection.

> **Research question.** Can uncertainty estimates from a candidate-level CT model identify
> focal pulmonary abnormalities for which LIDC-IDRI radiologists disagree about noduleness?

This is research software. It is **not** a clinical device, has no regulatory clearance, and
must not be used for diagnosis, screening, triage, or any clinical decision. No claim of
clinical utility is made anywhere in this project.

---

## Status

**Milestone 1 — pre-pilot readiness.** The study protocol is at `0.2.2-draft`, a procedural
amendment clarifying review authorization and archival history. The final freeze is pending.

| Gate | State |
|---|---|
| Documentation — full-text bibliography and phrase-overlap audit | **PASS** |
| Association freeze — the §4.5 threshold grid | **OPEN.** Thresholds are proposed, not frozen |
| Preprocessing / field-of-view freeze | **OPEN.** Declared, not frozen |

**The association pilot is not complete. No association threshold has been selected. No
reference labels or candidate dataset exist. No model has been trained and no evaluation
results exist under this protocol. The locked test set has never been accessed.**

The next scientific gate is **Gate 2A: authorization to begin reference review**, after human
implementation review and the private readiness checks in `docs/protocol.md` §15.B. Passing
synthetic tests does not authorize labelling, candidate construction, or training.

Everything published here is *design and tooling* committed **before** any label was created —
which is the property that makes the predeclared analysis credible.

## Documents

| File | What it is |
|---|---|
| [`docs/protocol.md`](docs/protocol.md) | The study protocol: design, predeclared outcomes, statistical procedure, gate status |
| [`docs/label_schema.md`](docs/label_schema.md) | What a label *means* — the four-category reader-vote target and its derivation rules |

## What is in this repository

```
docs/                  protocol and label schema
src/pilot/             association-pilot tooling (see below)
src/pylidc_compat.py   small compatibility shim for reading DICOM series metadata
scripts/               manifest builder, interface smoke test, private-split verifier
tests/                 90 tests, synthetic fixtures only — no patient data required
                       (patient-level split manifests are NOT distributed — see below)
```

### The association pilot

Candidates are built from the union of radiologist marks in a CT series. Deciding **which marks
refer to the same physical lesion** manufactures the `no_mark` votes the primary outcome is
computed from, so it is the study's most sensitive parameter — and LIDC publishes no matching
threshold. The pilot therefore builds a human-reviewed reference set to choose one:

- `xml_extract.py` — read-only extraction of reader marks from the annotation XML
- `pool.py` — the frozen eligibility predicate `d(i,j) <= max(12 mm, r_i + r_j)`
- `matching.py` — exact joint capacity-constrained selection by integral max-flow
- `manifest.py` — blinded reviewer manifests, private mappings, canonical hashing
- `review_store.py` — append-only, human-only decision storage
- `review_app.py` — a local blinded review interface
- `split_validation.py` — validation logic for patient-level split manifests, unit-tested
  against synthetic data; the real manifest is never published

## Reproducing

The LIDC-IDRI images and annotation XML are **not** redistributed here. Obtain them from
The Cancer Imaging Archive under their own terms:

- Collection DOI: `10.7937/K9/TCIA.2015.LO9QL9SX` (CC BY 3.0)
- Required citation: Armato III, S. G., et al. (2015). *Data From LIDC-IDRI* [Data set].
  The Cancer Imaging Archive.

Patient-level split manifests enumerate subject identifiers, including the locked-test
membership. They are **maintained locally and intentionally excluded from this repository**.
The default test suite therefore validates the split *logic* against synthetic data and needs
no patient data at all; verifying a real manifest is a separate, explicit step:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip check
python tests/run_tests.py
python scripts/pilot_ui_smoke.py

# Optional integration gate, against your own local manifest.
# Prints aggregate counts and hashes only, never subject identifiers,
# and exits 2 rather than reporting success if the manifest is not supplied.
python scripts/verify_private_split.py --manifest <path-to-your-private-manifest>

```

The validated local environment is macOS 15.6, arm64, Python 3.13.5, pip 25.1.1:
NumPy 2.5.3, matplotlib 3.11.2, pylidc 0.2.3, and setuptools 80.10.2. The complete synthetic
suite passes **90 tests, zero failures, zero skips**, and the interface smoke test passes
**20 checks**. The lock was resolved with uv 0.12.17 from the tested environment versions and
`requirements.txt`, with universal platform markers, then tested in a second clean virtual
environment. These checks validate the synthetic tooling, not a real-data pipeline.
`requirements.txt` retains the direct dependency requirements; the lock pins their resolved
dependencies for Python 3.13. Other Python versions are not validated by this snapshot.
Import `src.pylidc_compat` before `pylidc`, as the build script does.

GitHub Actions runs on Ubuntu with Python 3.13.5: it installs the lock, checks dependencies,
compiles tracked Python files, verifies imports, runs the full synthetic suite, and runs the
separate interface smoke test. CI needs no private data and does **not** verify the real
patient split, corpus, pilot manifests, or human implementation review. It downloads no LIDC
data. Private data and vault material remain excluded from the public repository.

The following manifest-builder command documents the tooling interface for a separately
authorized preparation step; it is **not part of the readiness checks** and does not authorize
rebuilding the frozen pilot manifests:

```bash
python scripts/build_pilot_manifest.py \
    --corpus <extracted-LIDC-XML-directory> \
    --out    <output-directory-outside-this-repository>
```

`--out` must resolve outside the repository; the script refuses anything inside it, including
the repository root and symlinks that resolve into it. Reviewer manifests, private mappings and
review records are deliberately written outside version control and are never published.

## Scope and limitations

- Single dataset. Generalisation beyond LIDC-IDRI is untested and is the project's main
  external-validity gap.
- LIDC labels are **reader-perceived**, not pathology-confirmed.
- Association geometry in the pilot parser is a within-series approximation; the production
  parser must use the full index-to-world transform.
- The association reference labels are a *human-reviewed operational association reference*,
  not clinical ground truth, and the reviewer is not a radiologist.

## Provenance

This code and documentation were **developed with AI assistance**, under the author's direction
and with the author's scientific decisions; a detailed private provenance record is maintained
outside this repository. Human line-by-line review of the implementation is **in progress and
not yet complete** — no part of this repository should be taken as independently verified code.

Methods used here are established prior work and are attributed in `docs/protocol.md` §2
(residual networks, multi-view CT patches, MC dropout, deep ensembles, temperature scaling,
Grad-CAM, saliency randomisation controls, the CLAIM reporting checklist). **No novelty is
claimed for uncertainty-based referral.** No implementation was copied from any paper or
repository.

## Licence

No licence has been chosen yet, so **all rights are reserved by default** and no permission to
reuse this code is granted at this time. LIDC-IDRI data and any imagery derived from it are
governed by TCIA's own terms and are **not** relicensed by this repository.

---

Author: Sarseej Shrestha
