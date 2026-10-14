# RxWatch: FDA Drug Shortage Status for Independent Pharmacies

RxWatch shows independent pharmacies the FDA shortage status, FDA-reported reasons, and supply facts for every drug in their inventory, using only free public FDA data.

## What it does

Upload an inventory CSV or search a single drug. For each drug, RxWatch shows:

- **FDA shortage status:** current, to be discontinued, resolved, or not on the shortage list
- **FDA-reported reasons**, shown verbatim when the FDA has stated one
- **Labeler count:** distinct companies listing the drug in the FDA NDC Directory, with a "Few labelers" flag when only 1 or 2 list it
- **Recall history** from FDA enforcement reports
- **Therapeutic class and dosage form**, when known
- **An experimental cause estimate** (supply-side vs demand-side), shown only for drugs in a current shortage with no FDA-stated reason and complete model inputs

Results are sorted by shortage status, then by fewest labelers. Every result shows the date of the underlying FDA data.

## What it does not do

RxWatch does not predict whether a drug will go into shortage. A drug that is not on the FDA shortage list can still become short. Always confirm supply with your wholesaler before making purchasing decisions.

## Research question

Most published shortage research relies on proprietary hospital or pharmacy purchasing data. This project asks:

> Can the cause of a drug shortage (supply-side vs demand-side) be predicted using only public FDA data?

### Approach

A logistic regression classifier with four features: manufacturer count (distinct NDC labelers), recall count, therapeutic category, and dosage form. Evaluation is done at the level of independent shortage events, using stratified grouped 5-fold cross-validation repeated over 10 seeds, plus a 1,000-permutation test against chance.

### Findings

| Result | Value |
|---|---|
| Labeled shortage events | 60 |
| Event-level AUC (mean, std) | 0.71 (0.13) |
| Permutation test p-value | 0.009 |
| Manufacturer count vs cause (Mann-Whitney U) | p = 0.307, not significant |
| Median labelers, supply-side vs demand-side | 9 vs 14 |

- The model beats chance, but the signal is weak and depends on a small sample.
- **Manufacturer concentration does not significantly differ by shortage cause** at the event level, even though supply-side shortages have lower median labeler counts.
- **The result is sensitive to a few events.** On the original 57 events, using the corrected data, the AUC is 0.64 (permutation p = 0.075). Almost all of the gain to 0.71 comes from three events that were added when the NDC data was completed.
- **Ingredient-grouped check:** TODO: fill in the AUC and permutation p from results.json, grouping cross-validation folds by active ingredient so related events (such as two rifampin shortages) never split across training and test.
- A finished-products-only version of manufacturer count (excluding bulk ingredient listings) gives similar results: AUC 0.70, permutation p = 0.013.

**Conclusion:** public FDA data alone gives a weak, sample-dependent signal for shortage cause. The main bottleneck is labeled data: only 421 of 1,627 shortage records (about 26%) state a reason, which leaves 60 usable independent events.

## How the results changed

An earlier version of this project reported much stronger results. Auditing them uncovered two data problems:

| Analysis | Unit of analysis | AUC | Permutation p | Mann-Whitney p |
|---|---|---|---|---|
| Original (row level) | 830 rows | 0.81 | not run | 3.68 × 10⁻¹⁰ |
| Duplicate records collapsed | 57 events | 0.63 | 0.094 | 0.298 |
| Complete NDC data | 60 events | 0.71 | 0.009 | 0.307 |

1. **Duplicate-record leakage.** The 830 training rows represented only 57 independent shortage events, because each shortage appeared many times across packages and companies. Row-level cross-validation put copies of the same event in both training and test folds, inflating the AUC, and the Mann-Whitney test treated duplicates as independent observations. Even the class balance was an artifact: rows looked 61% supply-side, but events are close to evenly split.
2. **Incomplete NDC data.** The paginated openFDA pull of the NDC Directory silently stopped on failed requests and was missing 14,415 of 138,427 records (10.4%). This surfaced when ursodiol, a common generic, appeared to have a single manufacturer. The data was replaced with openFDA's official bulk download, verified to match the live record count exactly.

An earlier version of the dashboard also showed "risk scores" and tiers derived from the model. These measured how strongly a drug leaned supply-side, not shortage risk, so they were removed in favor of FDA status and supply facts.

## Data

| Dataset | Records | Version |
|---|---|---|
| openFDA Drug Shortages | 1,627 | Snapshot pulled August 20, 2026 |
| openFDA Drug Enforcement Reports (recalls) | 10,156 | Report dates 2018 through August 2026, snapshot pulled August 20, 2026 |
| openFDA NDC Directory | 138,427 | Bulk export dated October 13, 2026 |

The shortages and recalls snapshots used for training are archived in `analysis/data/`. The openFDA shortages endpoint changes over time (records are added, revised, and removed), so the training data cannot be re-pulled and is reproducible only from the archived snapshot.

## Methodology notes

- **Shortage event:** one generic name plus initial posting date.
- **Event labels:** majority vote across distinct companies reporting the event. Exact ties are reported separately in `analysis/results.json`.
- **Rare categories:** therapeutic categories with fewer than 5 events are grouped as Other/Rare.
- **Sensitivity analyses** (all pre-declared, none replace the primary result): alternate category threshold, excluding the largest event, dropping events with mixed labels, finished-products-only manufacturer count, and active-ingredient grouping.

All statistics, including the original and superseded results, are recorded in `analysis/results.json`.

## Limitations

- **Small sample.** Only 60 labeled events, and results shift noticeably with a few events.
- **Timing of features.** Manufacturer counts are measured at data pull time, not at the time of each shortage. Some shortages date back to 2012.
- **Unknown class for most inventory drugs.** Therapeutic class is only known for drugs with FDA shortage history, so most common inventory drugs show Unknown.
- **Labeler counts include repackagers**, so they can overstate the number of independent manufacturers.
- **Approximate name matching.** Inventory names are matched to FDA records through normalization and fuzzy matching. Approximate matches are labeled in the dashboard so they can be verified.

## Project structure

```
RxWatch/
├── analysis/
│   ├── data/            # Archived August 20, 2026 shortages and recalls snapshots
│   ├── diagnostics/     # Diagnostic and sensitivity scripts
│   ├── figures/         # Generated figures
│   ├── results.json     # All reported statistics
│   └── validation.py    # Event-level validation pipeline
├── backend/             # FastAPI service: name matching, FDA lookups, model serving
│   ├── data/            # Pull script, metadata.json, trained model (raw CSVs are gitignored)
│   └── tests/           # pytest suite
└── frontend/            # Next.js dashboard
```

## Running locally

**Backend** (from the repo root):

```
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pandas scikit-learn joblib rapidfuzz
cd backend
python3 -m uvicorn main:app --reload --port 8000
```

**Frontend** (in a separate terminal):

```
cd frontend
pnpm install
pnpm dev
```

Create `frontend/.env.local` containing:

```
BACKEND_URL=http://localhost:8000
```

If pnpm reports ignored build scripts, run `pnpm approve-builds` and approve `msw`.

**Data:** raw data files are not included due to size. To regenerate the NDC Directory (uses the openFDA bulk download by default):

```
cd backend
python3 data/pull_openFDA_data.py ndc
```

**Tests:**

```
pip install pytest
cd backend
python3 -m pytest tests/ -v
```
