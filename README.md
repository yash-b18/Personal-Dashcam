# DashcamIQ

**Dashcam Anomaly Detection & Driver Scoring Platform**

DashcamIQ analyzes paired front and rear dashcam footage using computer vision, classical ML, and deep learning to detect driving anomalies and produce a quantified driver safety score — with AI-generated explanations for every incident detected.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Data Pipeline](#data-pipeline)
- [Models](#models)
- [Application Pages](#application-pages)
- [Branch Guide](#branch-guide)
- [Deployment](#deployment)
- [Environment Variables](#environment-variables)

---

## Overview

DashcamIQ processes 1,200+ paired front/rear dashcam MP4 clips stored on Cloudflare R2. It provides:

1. **Human-in-the-loop labeling** — review clips side-by-side, flag anomalies with reasons
2. **Three model tiers** — naive baseline, classical ML (XGBoost), and deep learning (YOLOv8 + LSTM)
3. **Driver scoring** — 100-point per-trip score with A–F grade
4. **AI explanations** — Claude-generated natural language descriptions of each anomaly
5. **Production web app** — dashboard, anomaly explorer, clip review interface

---

## Features

- Paired front + rear dashcam video synchronization via timestamp matching
- Anomaly types: hard braking, near-miss, lane departure, traffic violations, tailgating, harsh cornering, aggressive lane changes, distracted driving
- Per-trip and cumulative driver scores with trend tracking
- Admin labeling interface with keyboard shortcuts
- Async video processing via Celery + Redis
- Cloudflare R2 video storage integration (S3-compatible)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Next.js Frontend (Vercel)                      │
│  Dashboard │ Anomaly Explorer │ Labeling UI     │
└───────────────────┬─────────────────────────────┘
                    │ REST API
┌───────────────────▼─────────────────────────────┐
│  FastAPI Backend (Railway)                      │
│  Routes: videos │ anomalies │ labels │ scores   │
└────────┬──────────────────┬──────────────────────┘
         │                  │
┌────────▼──────┐  ┌────────▼──────────────────────┐
│ PostgreSQL    │  │ Celery + Redis (async tasks)   │
│ (Railway)     │  │ Video processing pipeline      │
└───────────────┘  └──────────────┬─────────────────┘
                                  │
┌─────────────────────────────────▼──────────────────┐
│  ML Pipeline                                       │
│  1. Optical Flow Baseline (no training)            │
│  2. XGBoost Feature Classifier                    │
│  3. YOLOv8 + LSTM Temporal Model                  │
└─────────────────────────────────┬──────────────────┘
                                  │
┌─────────────────────────────────▼──────────────────┐
│  Cloudflare R2 — Video Storage                    │
│  bucket/{main}/{front}/*.mp4                      │
│  bucket/{main}/{rear}/*.mp4                       │
└────────────────────────────────────────────────────┘
```

---

## Project Structure

```
dashcam-iq/
├── app.py                      # FastAPI entry point
├── requirements.txt            # All Python dependencies (pinned)
├── Makefile                    # venv, install, run, migrate, test shortcuts
├── setup.py                    # Environment validation + migration runner
├── .env.example                # Template for all required env vars
│
├── api/
│   ├── config.py               # Pydantic settings (reads from .env)
│   ├── database.py             # SQLAlchemy engine + get_db dependency
│   ├── models/
│   │   └── db_models.py        # ORM tables: Clip, Label, Anomaly, Score, OverallDriverScore
│   ├── routes/                 # FastAPI routers (videos, anomalies, labels, scores, health)
│   ├── storage/
│   │   ├── r2_client.py        # Cloudflare R2 client (list, download, presigned URLs)
│   │   └── clip_pairer.py      # Pairs front/rear clips by timestamp matching
│   ├── tasks/
│   │   ├── celery_app.py       # Celery app configuration
│   │   └── video_tasks.py      # Async video processing task stubs
│   └── video/
│       └── frame_extractor.py  # ffprobe metadata + OpenCV frame extraction
│
├── scripts/
│   ├── make_dataset.py         # R2 ingestion script (pairs + upserts to DB)
│   ├── build_features.py       # Feature extraction pipeline
│   ├── model.py                # Train / predict orchestration CLI
│   ├── scoring.py              # Scoring engine + grade assignment
│   ├── genai.py                # Claude API explanation generator
│   └── models/
│       ├── baseline.py         # Naive optical flow detector
│       ├── classical.py        # XGBoost classifier
│       └── deep_learning.py    # YOLOv8 + LSTM classifier
│
├── models/                     # Saved model weights (.pt, .pkl)
├── data/
│   ├── raw/                    # Local video cache (gitignored)
│   ├── processed/              # Extracted features (.npz files)
│   └── outputs/                # Inference results, scores, experiment plots
│       └── experiment/         # Training sensitivity analysis outputs
├── notebooks/                  # EDA and experiment notebooks (not graded)
├── tests/                      # pytest unit + integration tests
├── alembic/                    # Database migration scripts
└── frontend/                   # Next.js web application
```

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- FFmpeg (`brew install ffmpeg` on macOS)
- PostgreSQL (or use Railway)
- Redis (or use Railway)

### Backend

```bash
# Clone the repo
git clone https://github.com/yash-b18/Personal-Dashcam.git
cd Personal-Dashcam

# Create and activate virtual environment (never install globally)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt

# Copy env template and fill in values
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app:app --reload

# Start Celery worker (separate terminal, with venv activated)
celery -A api.tasks.celery_app worker --loglevel=info
```

Or use the Makefile shortcuts:

```bash
make install    # creates venv + installs requirements
make migrate    # runs alembic upgrade head
make run        # starts uvicorn
make worker     # starts celery worker
make test       # runs pytest
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # fill in API URL
npm run dev
```

---

## Data Pipeline

### R2 Bucket Structure

DashcamIQ expects your Cloudflare R2 bucket to follow this layout:

```
bucket/
└── {R2_MAIN_FOLDER}/
    ├── {R2_FRONT_FOLDER}/     # default: "front"
    │   ├── 20240101_120000.mp4
    │   ├── 20240101_120300.mp4
    │   └── ...
    └── {R2_REAR_FOLDER}/      # default: "rear"
        ├── 20240101_120000.mp4
        ├── 20240101_120300.mp4
        └── ...
```

### Clip Pairing

Front and rear clips are matched by **timestamp extracted from the filename**. The pairer handles common dashcam naming formats:

| Format | Example |
|--------|---------|
| `YYYYMMDD_HHMMSS` | `20240101_120000.mp4` |
| `YYYY_MM_DD_HH_MM_SS` | `2024_01_01_12_00_00.mp4` |
| `YYYY-MM-DD_HH-MM-SS` | `2024-01-01_12-00-00.mp4` |
| Prefix + timestamp | `REC_20240315_083045.mp4` |

Clips whose timestamps are within **5 seconds** of each other are paired. The tolerance is configurable in `api/storage/clip_pairer.py`.

### Ingestion Script

```bash
# Preview pairs without writing to DB
python scripts/make_dataset.py --dry-run

# Ingest all clips with duration metadata (slower — downloads each clip)
python scripts/make_dataset.py

# Fast ingest — skip ffprobe duration extraction
python scripts/make_dataset.py --no-metadata

# Test with a small batch first
python scripts/make_dataset.py --limit 20 --dry-run
```

The script is **idempotent** — safe to re-run. Existing clips are updated; new clips are inserted with `PENDING` processing status.

### Frame Extraction

`api/video/frame_extractor.py` provides:
- `get_metadata()` — duration, fps, resolution, codec via ffprobe (no full decode)
- `extract_frames(target_fps)` — lazy frame generator via OpenCV (never loads full video into memory)
- `extract_clip_segment()` — cuts a short anomaly clip snippet via ffmpeg for display in the UI

---

## Models

### 1. Naive Baseline (`scripts/models/baseline.py`)
Dense optical flow (Farneback) magnitude thresholding. No training required. Processes frames at 640px wide for speed, flags clips where inter-frame motion or motion variance exceeds calibrated thresholds, and merges overlapping windows into clean anomaly segments with timestamps and severity scores.

```bash
# Run on a single local video
python scripts/model.py --predict --model baseline --video path/to/clip.mp4

# Run on all pending clips in the DB (downloads from R2)
python scripts/model.py --predict --model baseline

# Evaluate against labeled clips (requires labeled data from admin UI)
python scripts/model.py --evaluate --model baseline
```

Key thresholds (tunable in `scripts/models/baseline.py`):
- `MAGNITUDE_THRESHOLD = 12.0` — mean flow magnitude (px/frame) to flag a window
- `VARIANCE_THRESHOLD = 6.0` — std dev spike to flag erratic motion
- `WINDOW_SIZE_FRAMES = 30` — ~1 second at 30fps
- Results saved to `data/outputs/baseline_results.json`

### 2. Classical ML (`scripts/models/classical.py`)
19 hand-crafted features extracted from optical flow, edge density, and motion blur → XGBoost binary classifier (+ Random Forest for comparison). Features are pre-extracted and cached as `.npz` files so training is fast.

```bash
# Step 1: extract features for all clips (downloads from R2, saves to data/processed/)
python scripts/build_features.py --all

# Step 2: train XGBoost + Random Forest with 5-fold CV (requires labeled clips)
python scripts/model.py --train --model classical

# Step 3: predict on all clips
python scripts/model.py --predict --model classical
```

Feature groups: optical flow magnitude stats, window-level peaks, motion direction variance, motion blur (Laplacian), edge density changes, temporal spike patterns. Results and feature importances saved to `data/outputs/classical_eval.json`.

### 3. Deep Learning (`scripts/models/deep_learning.py`)
YOLOv8 per-frame object detection → 13-dim per-frame feature sequences → 2-layer bidirectional LSTM classifier. Outputs anomaly probability per 30-frame sliding window; clip is flagged if any window exceeds threshold.

**Stage 1 — Feature Extraction** (`api/video/sequence_builder.py`):
- Runs YOLOv8 (`yolov8m.pt`) on every frame to detect vehicles, pedestrians, cyclists, traffic lights, stop signs
- Computes dense optical flow (Farneback) between consecutive frames
- Per-frame 13-dim feature vector: object counts + proximity scores + flow magnitude/direction + motion blur + edge density
- Sliding window: 30 frames (~1 sec at 30fps), 50% overlap → shape `(n_windows, 30, 13)`
- Sequences cached as `data/processed/{clip_id}_dl_features.npz`

**Stage 2 — LSTM Classifier** (`scripts/models/deep_learning.py`):
- Bidirectional LSTM (2 layers, hidden=128 → 256 bidirectional output)
- Mean temporal pooling → FC head (256 → 64 → 1)
- Training: BCEWithLogitsLoss with `pos_weight` for class imbalance, AdamW, CosineAnnealingLR, early stopping on val F1 (patience=10)
- Data augmentation: Gaussian noise on features during training

```bash
# Step 1: extract DL feature sequences for all labeled clips (downloads from R2)
python scripts/model.py --extract-dl-features --model deep_learning

# Step 1b: extract from a single local video
python scripts/model.py --extract-dl-features --model deep_learning --video path/to/clip.mp4

# Step 2: train the LSTM (requires labeled clips + extracted features)
python scripts/model.py --train --model deep_learning

# Step 3: predict on all clips with pre-extracted features
python scripts/model.py --predict --model deep_learning

# Step 3b: end-to-end inference on a single video (no pre-extraction needed)
python scripts/model.py --predict --model deep_learning --video path/to/clip.mp4
```

Key parameters (tunable in `scripts/models/deep_learning.py`):
- `HIDDEN_DIM = 128` — LSTM hidden units per direction
- `SEQUENCE_LENGTH = 30` — frames per window
- `DECISION_THRESHOLD = 0.5` — anomaly probability cutoff
- Model weights saved to `models/dl_lstm.pt`
- Training history (loss/F1/AUC per epoch) saved to `data/outputs/dl_eval.json`

### Experiment — Training Set Size Sensitivity Analysis (`scripts/experiment.py`)
Answers: *"How many labeled clips do we need before each model becomes reliable?"*

- Trains both Classical (XGBoost) and Deep Learning (LSTM) at **10%, 25%, 50%, 75%, and 100%** of available labeled data
- Each fraction repeated N times (default 3) with different seeds for error bars
- Fixed held-out test set (20% of labeled data) used across all fractions
- Metrics: F1, AUC-ROC, Precision, Recall — mean ± std per fraction
- Outputs a data-driven recommendation: minimum fraction to reach F1 ≥ 70%

```bash
# Run full experiment (both models, 3 repeats per fraction)
python scripts/experiment.py

# Classical only (faster, no GPU needed)
python scripts/experiment.py --model classical

# Fewer repeats for quick iteration
python scripts/experiment.py --n-repeats 1

# Custom features directory
python scripts/experiment.py --features-dir data/processed --output-dir data/outputs/experiment
```

Outputs saved to `data/outputs/experiment/`:
- `experiment_results.json` — all metrics with mean ± std per fraction
- `experiment_f1.png` — F1 learning curves with error bands
- `experiment_auc.png` — AUC-ROC learning curves with error bands
- `experiment_combined.png` — side-by-side F1 + AUC panel plot

---

## Scoring & AI Explanations

### Scoring Engine (`scripts/scoring.py`)
Converts anomaly detections into a 0–100 driving score per clip and an exponentially weighted overall score.

- **Per-clip score**: Base 100, deductions per anomaly = `severity × MAX_DEDUCTIONS[type]`
- **Same-type cap**: Multiple anomalies of the same type capped at `1.5 × MAX_DEDUCTIONS[type]` to prevent runaway deductions
- **Overall score**: Exponential recency weighting (`decay=0.9`) — recent trips count more

| Anomaly Type | Max Deduction |
|---|---|
| Traffic violation | 30 pts |
| Near-miss | 25 pts |
| Lane departure | 20 pts |
| Distracted driving | 20 pts |
| Hard braking | 15 pts |
| Tailgating | 15 pts |
| Aggressive lane change | 15 pts |
| Hard acceleration | 10 pts |
| Harsh cornering | 10 pts |

Grades: A ≥ 90 · B ≥ 80 · C ≥ 70 · D ≥ 60 · F < 60

### AI Explanations (`scripts/genai.py`)
Calls `claude-sonnet-4-6` to generate natural language explanations for each detected anomaly.

Each explanation includes:
1. **What happened** — 2–3 sentence description of the event and why it's a safety concern
2. **Recommendation** — one specific, actionable tip for the driver
3. **Score impact** — plain-language statement of points deducted

Responses are cached in the DB (`anomalies.ai_explanation`) so the API is only called once per anomaly. Requires `ANTHROPIC_API_KEY` in `.env`.

---

## API Endpoints

Base URL: `/api/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/videos` | List all clips (paginated, filter by status) |
| GET | `/videos/{id}` | Clip detail + presigned front/rear video URLs |
| POST | `/videos/{id}/process` | Enqueue clip for ML processing (Celery) |
| POST | `/videos/process-all` | Enqueue all pending clips |
| GET | `/anomalies` | List anomalies (filter by type, model, severity) |
| GET | `/anomalies/{id}` | Anomaly detail with AI explanation |
| GET | `/labels/queue` | Next batch of unlabeled clips for review |
| POST | `/labels/{clip_id}` | Submit thumbs up/down label |
| PUT | `/labels/{clip_id}` | Update an existing label |
| DELETE | `/labels/{clip_id}` | Remove label (return clip to queue) |
| GET | `/scores/overall` | Current overall driver score + grade |
| GET | `/scores/history` | Per-clip score history for trend charts |
| GET | `/scores/dashboard` | All dashboard data in one call |
| POST | `/scores/recalculate` | Force recompute overall score |
| GET | `/health` | API health check |

### Celery Processing Pipeline (`api/tasks/video_tasks.py`)
Triggered via `POST /videos/{id}/process`:
1. Download front video from Cloudflare R2
2. Run optical flow baseline detector
3. Map anomaly windows → AnomalyType heuristic
4. Compute clip driving score (deductions by severity)
5. Generate Claude AI explanation per anomaly window
6. Persist Anomaly + Score rows to PostgreSQL
7. Update clip status → DONE (or FAILED on error, with 3 auto-retries)

## Application Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | Driver score gauge, trend chart, anomaly breakdown by type, recent incidents feed |
| Anomaly Explorer | `/anomalies` | Grid of detected anomalies with video clips + AI-generated explanations |
| Video Library | `/trips` | All processed clips with per-trip scores and processing status |
| Labeling Interface | `/admin/label` | Side-by-side synced front/rear player with thumbs up/down labeling + keyboard shortcuts |

---

## Branch Guide

| Branch | Status | Description |
|--------|--------|-------------|
| `feature/project-setup` | ✅ Merged | Repo scaffolding, DB models, config, requirements, README |
| `feature/data-pipeline` | ✅ Merged | R2 client, timestamp-based clip pairing, frame extraction, ingestion script |
| `feature/naive-baseline` | ✅ | Optical flow thresholding anomaly detector |
| `feature/classical-ml` | ✅ | 19-feature extraction pipeline + XGBoost + Random Forest classifier |
| `feature/deep-learning` | ✅ | YOLOv8 object detection + LSTM temporal classifier |
| `feature/experiment` | ✅ | Training set size sensitivity analysis |
| `feature/scoring-genai` | ✅ | Scoring engine + Claude API explanation generation |
| `feature/api-backend` | ✅ | Full FastAPI routes, Celery tasks, video streaming |
| `feature/frontend-core` | 🔜 | Next.js setup, layout, design system |
| `feature/frontend-labeling` | 🔜 | Admin clip review UI (side-by-side player, thumbs up/down) |
| `feature/frontend-dashboard` | 🔜 | Driver dashboard (score gauge, charts, trip history) |
| `feature/frontend-anomalies` | 🔜 | Anomaly explorer + detail view with synced player |
| `feature/deployment` | 🔜 | Docker, Railway config, Vercel config, CI/CD |

---

## Deployment

- **Frontend**: Vercel (Next.js)
- **Backend**: Railway (FastAPI + PostgreSQL + Redis)
- **Video Storage**: Cloudflare R2 (existing)

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values. Never commit `.env`.

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 API access key |
| `R2_SECRET_ACCESS_KEY` | R2 API secret key |
| `R2_BUCKET_NAME` | Your R2 bucket name |
| `R2_PUBLIC_URL` | Public URL for the bucket |
| `R2_MAIN_FOLDER` | Top-level folder in bucket (e.g. `dashcam`) |
| `R2_FRONT_FOLDER` | Front camera subfolder name (default: `front`) |
| `R2_REAR_FOLDER` | Rear camera subfolder name (default: `rear`) |
| `ANTHROPIC_API_KEY` | Claude API key for anomaly explanations |
| `SECRET_KEY` | App secret for token signing |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |

---

## License

Duke University — CS Deep Learning Final Project
