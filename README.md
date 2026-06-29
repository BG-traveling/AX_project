# 🌀 TyphoonPath — AI-Powered Typhoon Path Prediction

> Interactive typhoon path prediction service powered by LSTM deep learning, GBM machine learning, and real IBTrACS historical data.

---

## 📌 Overview

TyphoonPath lets users set a typhoon's starting point and meteorological conditions on a map, then predicts the path using a 4-level AI model chain. Built as part of an AX automation project over 3 days using the BMAD methodology.

**Live Demo:** _Coming soon (Railway + Vercel)_

---

## 🖥️ Screenshots

| Map View | Prediction Result |
|----------|------------------|
| Set start point + conditions | Intensity-colored path + timeline |

---

## ⚙️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Leaflet.js |
| Backend | FastAPI (Python 3.11+) |
| ML / DL | PyTorch (LSTM), scikit-learn (GBM) |
| AI Commentary | Claude Haiku (Anthropic API) |
| Cache | Redis |
| Data | IBTrACS WP — NOAA (1951–2024, 2,645 typhoons) |
| Deploy | Vercel (Frontend) · Railway (Backend + Redis) |

---

## 🤖 Prediction Model — 4-Level Fallback Chain

```
Request
  ↓
① LSTM Seq2Seq + Bahdanau Attention  (ensemble: hidden=48/64/96)
  ↓ fallback if < 5 points
② GradientBoosting ML  (3 models: dlat / dlng / dpres)
  ↓ fallback
③ Analog Blending  (top-10 similar historical typhoons, weighted avg)
  ↓ fallback
④ Physics Model  (beta drift + SST-based intensity)
```

### LSTM Architecture
- **Encoder**: 4 steps (24h history) × 8 features → hidden state
- **Attention**: Bahdanau attention over encoder outputs
- **Decoder**: Auto-regressive, up to 40 steps (240h = 10 days)
- **Features**: `dlat, dlng, dpres, lat_norm, lng_norm, pres_norm, sin_month, cos_month`
- **Training**: L1Loss · Adam(lr=0.001) · CosineAnnealingLR · Early stopping (patience=12)

### GBM Features (11)
`lat, lng, pressure, wind_1min_ms, wind_10min_ms, diameter_km, month, prev_dlat, prev_dlng, lat×sin(month), lat×cos(month)`

---

## 📦 Dataset

| Item | Value |
|------|-------|
| Source | IBTrACS WP v04r01 (NOAA) |
| Typhoons | 4,230 (enhanced) |
| Period | 1951 – 2024 |
| Track points | 172,206+ |
| Fields added | `wind_1min_ms`, `wind_10min_ms`, `diameter_km` |

---

## 🗂️ Project Structure

```
AX_project/
├── frontend/                  # React + TypeScript
│   └── src/
│       ├── App.tsx            # Main app + 3-phase UX flow
│       ├── api/typhoonApi.ts  # API client
│       ├── types/typhoon.ts   # Type definitions
│       └── components/Map/
│           └── TyphoonMap.tsx # Leaflet map + intensity segments
│
├── backend/                   # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   └── predict.py     # 4-level fallback chain
│   │   ├── services/
│   │   │   ├── lstm_prediction_service.py
│   │   │   ├── ml_prediction_service.py
│   │   │   ├── blend_service.py
│   │   │   └── claude_service.py
│   │   └── models/schemas.py
│   ├── data/
│   │   ├── typhoons_v2.json   # Enhanced dataset (39MB)
│   │   ├── track_model_lat.pkl
│   │   ├── track_model_lng.pkl
│   │   ├── pres_model.pkl
│   │   └── lstm_model_h*.pt   # LSTM ensemble weights
│   └── scripts/
│       ├── convert_data.py    # IBTrACS CSV → typhoons.json
│       ├── enhance_data.py    # Add wind/diameter fields
│       ├── train_model.py     # Train GBM models
│       └── train_lstm.py      # Train LSTM ensemble
│
└── docs/                      # BMAD project docs
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Redis

### 1. Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Create `backend/.env`:
```env
ANTHROPIC_API_KEY=your_key_here
REDIS_URL=redis://localhost:6379
```

### 2. Train Models (first time only)

```bash
# Step 1: Convert raw CSV to JSON (skip if typhoons.json already exists)
python scripts/convert_data.py

# Step 2: Add wind/diameter fields
python scripts/enhance_data.py

# Step 3: Train GBM models (~2 min)
python scripts/train_model.py

# Step 4: Train LSTM ensemble (~10–30 min)
pip install torch --index-url https://download.pytorch.org/whl/cpu
python scripts/train_lstm.py
```

### 3. Run Backend

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

---

## 🗺️ How to Use

1. **Click on the map** to set the typhoon's starting point
2. **Adjust sliders** — pressure, SST, 1-min wind, 10-min wind, diameter
3. **Click "경로 예측하기"** to run prediction
4. **View results**:
   - Intensity-colored path (STY=red / TY=orange / TS=yellow / TD=blue)
   - `+1일`, `+2일`... time labels every 24h
   - Click any point for details (time, intensity, pressure, wind speed)
   - Sidebar shows method badge, duration, intensity timeline bar
   - AI weather commentary from Claude Haiku

---

## 🔄 Prediction Method Badge

| Badge | Method | Condition |
|-------|--------|-----------|
| 🧠 LSTM 딥러닝 | LSTM Seq2Seq+Attention | `.pt` model files present |
| 🤖 GBM 머신러닝 | GradientBoosting | `.pkl` model files present |
| 📊 유사 태풍 블렌딩 | Analog Blending | Historical data match found |
| ⚙️ 물리 모델 | Physics | Always available (fallback) |

---

## 🐛 Known Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| STY intensity never weakens | Pressure model kept strengthening | `lifecycle_dpres()` 3-phase model |
| ML model never loads after training | `@lru_cache` caches `None` | Global dict, only stores on success |
| Complex number error in training | Negative base with fractional exponent | `max(0, 1010 - pres)` clamping |

---

## 📄 License

MIT

---

## 👤 Author

**김동현** · [onthegroundplay403@gmail.com](mailto:onthegroundplay403@gmail.com)

> Built with BMAD methodology (Analyst → PM → Architect → Scrum Master → Developer)
