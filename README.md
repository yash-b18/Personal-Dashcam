# DashcamIQ

**Dashcam Anomaly Detection & Driver Scoring Platform**

DashcamIQ analyzes paired front and rear dashcam footage using computer vision, classical ML, and deep learning to detect driving anomalies and produce a quantified driver safety score — with AI-generated explanations for every incident detected.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Setup](#setup)
- [Branch Guide](#branch-guide)
- [Models](#models)
- [Application Pages](#application-pages)
- [Deployment](#deployment)

---

## Overview

DashcamIQ processes 1,200+ paired front/rear dashcam MP4 clips stored on Cloudflare R2. It provides:

1. **Human-in-the-loop labeling** — review clips, flag anomalies with reasons
2. **Three model tiers** — naive baseline, classical ML (XGBoost), and deep learning (YOLOv8 + LSTM)
3. **Driver scoring** — 100-point per-trip score with A–F grade
4. **AI explanations** — Claude-generated natural language descriptions of each anomaly
5. **Production web app** — dashboard, anomaly explorer, clip review interface

---

## Features

- Paired front + rear dashcam video synchronization
- Anomaly types: hard braking, near-miss, lane departure, traffic violations, tailgating, harsh cornering, aggressive lane changes
- Per-trip and cumulative driver scores with trend tracking
- Admin labeling interface with keyboard shortcuts
- Async video processing via Celery + Redis
- Cloudflare R2 video storage integration

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
└───────────────┘  └────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────┐
│  ML Pipeline                                       │
│  1. Optical Flow Baseline                         │
│  2. XGBoost Feature Classifier                    │
│  3. YOLOv8 + LSTM Temporal Model                  │
└────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────┐
│  Cloudflare R2 — Video Storage                    │
└────────────────────────────────────────────────────┘
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

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and fill in values
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app:app --reload

# Start Celery worker (separate terminal, venv activated)
celery -A api.tasks.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local  # fill in API URL
npm run dev
```

---

## Branch Guide

| Branch | Description |
|--------|-------------|
| `feature/project-setup` | ✅ Repo scaffolding, DB models, config, requirements, README |
| `feature/data-pipeline` | ✅ Cloudflare R2 client, timestamp-based clip pairing, frame extraction, ingestion script |
| `feature/naive-baseline` | Optical flow thresholding anomaly detector |
| `feature/classical-ml` | Feature extraction + XGBoost/Random Forest classifier |
| `feature/deep-learning` | YOLOv8 object detection + LSTM temporal classifier |
| `feature/experiment` | Training set size sensitivity analysis |
| `feature/scoring-genai` | Scoring engine + Claude API explanation generation |
| `feature/api-backend` | FastAPI routes, Celery tasks, video streaming |
| `feature/frontend-core` | Next.js setup, layout, design system |
| `feature/frontend-labeling` | Admin clip review UI (side-by-side player, thumbs up/down) |
| `feature/frontend-dashboard` | Driver dashboard (score gauge, charts, trip history) |
| `feature/frontend-anomalies` | Anomaly explorer + detail view |
| `feature/deployment` | Docker, Railway config, Vercel config, CI/CD |

---

## Models

### 1. Naive Baseline (`scripts/models/baseline.py`)
Dense optical flow (Farneback) magnitude thresholding. No training required. Flags clips where inter-frame motion exceeds calibrated thresholds.

### 2. Classical ML (`scripts/models/classical.py`)
Feature extraction from optical flow statistics and YOLOv8 detections → XGBoost binary classifier. Trains on human-labeled clips.

### 3. Deep Learning (`scripts/models/deep_learning.py`)
YOLOv8 per-frame object detection + ByteTrack object tracking → per-frame feature sequences → 2-layer LSTM temporal classifier. Outputs anomaly probability and type.

### Experiment
Training set size sensitivity analysis: F1 and AUC-ROC measured at 10%, 25%, 50%, 75%, and 100% of labeled data. Results in `data/outputs/experiment/`.

---

## Application Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | Driver score gauge, trend chart, anomaly breakdown, recent incidents |
| Anomaly Explorer | `/anomalies` | Grid of detected anomalies with clips + AI explanations |
| Video Library | `/trips` | All processed clips with scores and processing status |
| Labeling Interface | `/admin/label` | Side-by-side front/rear player with thumbs up/down labeling |

---

## Deployment

- **Frontend**: Vercel (Next.js)
- **Backend**: Railway (FastAPI + PostgreSQL + Redis)
- **Video Storage**: Cloudflare R2 (existing)

---

## Data Ingestion

Once your `.env` is configured with R2 credentials, run:

```bash
# Preview without writing to DB
python scripts/make_dataset.py --dry-run

# Ingest all clips (downloads front clip briefly to get duration)
python scripts/make_dataset.py

# Fast ingest — skip duration extraction
python scripts/make_dataset.py --no-metadata
```

The script pairs front/rear clips by matching timestamps in filenames.
Clips are identified by datetime embedded in the filename (e.g. `20240101_120000.mp4`).
Front and rear clips within 5 seconds of each other are paired automatically.

## Environment Variables

See `.env.example` for all required configuration values.

Key R2 variables:
- `R2_MAIN_FOLDER` — top-level folder in your bucket (e.g. `dashcam`)
- `R2_FRONT_FOLDER` — subfolder for front camera clips (default: `front`)
- `R2_REAR_FOLDER` — subfolder for rear camera clips (default: `rear`)

---

## License

Duke University — CS Deep Learning Final Project
