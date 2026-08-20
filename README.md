# RxWatch

**Predicting the cause of drug shortages from public FDA data, for pharmacies that don't have access to proprietary purchasing data.**

Independent pharmacies face the same unpredictable drug shortage environment as hospital systems, but without the purchasing infrastructure or data access that existing shortage-prediction tools rely on. RxWatch investigates whether the *cause* of a drug shortage (supply-side vs. demand-side) can be predicted using only free, public FDA data, and turns that into a working dashboard a pharmacy can actually use.

**Status:** In progress. Core analysis, model, and a working end-to-end dashboard are complete. See [Known Limitations](#known-limitations) below.

## The Question

Most existing shortage-prediction research either requires proprietary hospital/pharmacy purchasing data, or predicts *whether* a shortage will happen without addressing *why*. This project asks:

> Can shortage cause be predicted from a drug's characteristics at the time it's reported (manufacturer concentration, recall history, therapeutic class, dosage form) using only public FDA regulatory data?

## Key Finding

Manufacturer concentration significantly predicts shortage cause. Supply-side shortages cluster at low manufacturer counts; demand-side shortages show a much wider spread (Mann-Whitney U test, p = 3.68 × 10⁻¹⁰). A 4-feature logistic regression model built entirely on public data reaches a cross-validated AUC of 0.81, competitive with published studies that use proprietary institutional data.

Full methodology, results, and limitations are written up in [`report.tex`](./analysis/report.tex) (not added yet)

## Project Structure

```
RxWatch/
├── analysis/          # Jupyter notebook: data pipeline, feature engineering, model training
├── backend/            # FastAPI service that serves the trained model
│   └── data/            # Raw CSVs + trained model (.gitignored - see below)
├── frontend/           # Next.js dashboard (landing page + inventory scoring tool)
└── report.tex          # Full research write-up
```

## How It Works

1. **Data**: Three openFDA datasets (Drug Shortages, Enforcement/Recalls, NDC Directory) pulled via the openFDA REST API.
2. **Model**: A logistic regression classifier trained on manufacturer count, recall count, therapeutic category, and dosage form, predicting whether a shortage is supply-side or demand-side driven.
3. **Backend**: FastAPI serves the trained model, handles drug name search/matching (including brand-name lookup), and generates plain-language guidance via a constrained LLM call (grounded only in model-computed facts, no invented statistics or supplier names).
4. **Frontend**: A Next.js dashboard where a pharmacy can search a single drug or upload their full inventory and get back a ranked risk table.

## Running Locally

**Backend:**
```bash
cd backend
pip install fastapi uvicorn pandas scikit-learn joblib --break-system-packages
python3 -m uvicorn main:app --reload --port 8000
```

**Frontend** (in a separate terminal):
```bash
cd frontend
npm install
npm run dev
```

You'll need your own `.env.local` in `frontend/` with:
```
BACKEND_URL=http://localhost:8000
OPENAI_API_KEY=your_key_here
```

Raw data files (`backend/data/*.csv`, `*.json`) are not included in this repo due to size; the pull script (`data/pull_openFDA_data.py`) can regenerate them from the openFDA API.

## Known Limitations

- **Scope**: the model is trained only on the ~26% of shortage records with a stated reason. It does not predict *whether* a drug will enter shortage, only the likely cause for drugs already in the shortage dataset.
- **Drug class/dosage form coverage**: frequently shows as "Unknown" for drugs without prior shortage history, due to a name-formatting mismatch between the shortages dataset and the NDC directory (not yet resolved).
- **Public-data tradeoff**: performance (AUC 0.81) sits below models trained on proprietary institutional data (e.g., UNC AJHP's 0.93 C-statistic), an expected tradeoff given this project's public-data-only scope.

Full discussion in the [Limitations section](./report.tex) of the write-up.

## Related Work

This project builds on and differentiates from prior shortage-prediction research, including hospital procurement models (China), pharmacy dispensing models (Canada), and institutional purchasing models (UNC). See the Literature Review in the full report for details.
