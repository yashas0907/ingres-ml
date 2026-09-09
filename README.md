# INGRES — AI + ML Powered Intelligent Groundwater Analysis and Prediction System

INGRES is a full-stack AI and Machine Learning platform that analyzes India's groundwater crisis. It combines a conversational AI assistant, trained ML models, interactive dashboards, and data visualizations to provide actionable groundwater intelligence.

---

## Features

### AI Chat Assistant
- Conversational interface powered by Meta Llama 3 (via HuggingFace Inference API)
- Semantic search using sentence-transformers for intelligent context retrieval
- Real-time streaming responses (Server-Sent Events)
- Natural language queries about any Indian state or district

### ML Risk Classification
- Classifies districts as Safe / Semi-Critical / Critical / Over-Exploited
- Models: SVM (97.5% accuracy), Random Forest (100%), Decision Tree (100%)
- Features: extraction %, recharge level, rainfall, population density
- Best model automatically selected and saved

### ML Extraction Forecasting
- Predicts future groundwater extraction levels for any year up to 2035
- Models: Linear Regression (RMSE 28.0, R2 0.10), Random Forest (RMSE 15.8, R2 0.71)
- 6-year trend forecast visualization
- State-aware feature estimation

### Interactive Dashboard
- National overview statistics (total blocks, states, over-exploited %)
- Category distribution doughnut chart
- Top 10 most stressed districts bar chart
- ML model performance comparison table
- Feature importance visualization

### Trend Analysis
- Historical extraction data for all Indian states (2017-2022)
- Multi-state line chart comparison
- Filter by risk category
- Color-coded extraction table

### District Comparison
- Side-by-side comparison of up to 6 states/districts
- Bar and Radar chart views
- Extraction vs. estimated recharge comparison

### Interactive India Map
- Color-coded groundwater depth visualization
- State-level and district-level drill-down
- Contaminant data per region

---

## Architecture

```
INGRES/
├── Backend/
│   ├── main.py                        # FastAPI app, AI chat endpoints, CORS
│   ├── ingest_data.py                 # CSV to MongoDB ingestion
│   ├── migrate_to_mongodb.py          # SQLite to MongoDB migration tool
│   ├── india_groundwater_2022.csv     # Block-level assessment data
│   ├── india_groundwater_trends.csv   # State-level historical trends
│   ├── ml/
│   │   ├── dataset.py                 # Synthetic + real data generator
│   │   ├── classifier.py              # SVM + RF + DT classifier pipeline
│   │   ├── regressor.py               # Linear + RF regression pipeline
│   │   └── train.py                   # Training script (run once)
│   ├── models/
│   │   ├── best_classifier.pkl        # Best trained classifier
│   │   ├── best_regressor.pkl         # Best trained regressor
│   │   └── training_summary.json      # Accuracy/RMSE/R2 metrics
│   └── routers/
│       └── ml_routes.py               # /api/ml/* endpoints
│
└── Frontend/
    ├── src/
    │   ├── App.jsx                    # Main app with tab navigation
    │   ├── App.css                    # Styling
    │   ├── pages/
    │   │   ├── Dashboard.jsx          # ML dashboard with stats + charts
    │   │   ├── Predictions.jsx        # Risk classification + forecast UI
    │   │   ├── TrendAnalysis.jsx      # Historical trend charts + table
    │   │   └── Comparison.jsx         # District comparison UI
    │   ├── components/
    │   │   ├── WebGLWaves.jsx         # Animated background
    │   │   └── MapLegend.jsx          # Map depth legend
    │   ├── utils/
    │   │   └── api.js                 # API base URL helper
    │   └── data/                      # Static map data
    ├── vite.config.js
    └── package.json
```

---

## API Reference

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ask` | Streaming AI groundwater Q&A |
| GET | `/get-news` | Latest groundwater news |
| GET | `/` | Health check |

### ML APIs (/api/ml/)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/predict-risk` | Classify groundwater risk category |
| POST | `/predict-groundwater` | Forecast future extraction level |
| GET | `/top-risk-districts` | Most over-exploited districts |
| GET | `/district-distribution` | Category breakdown counts |
| GET | `/trend-analysis` | Historical trends for all states |
| POST | `/compare-districts` | Compare multiple states/districts |
| GET | `/model-stats` | ML model accuracy/RMSE/R2 metrics |
| GET | `/overview-stats` | National summary statistics |

### Prediction Request Example

```json
POST /api/ml/predict-risk
{
  "extraction_pct": 135,
  "state": "Punjab"
}

Response:
{
  "category": "Over-Exploited",
  "category_index": 3,
  "probabilities": { "Safe": 0.0, "Semi-Critical": 0.0, "Critical": 0.2, "Over-Exploited": 99.8 },
  "color": "#e74c3c"
}
```

---

## ML Workflow

1. **Data Generation** — `Backend/ml/dataset.py` generates 6,000 training samples using real extraction data from the MongoDB database plus realistic synthetic augmentation
2. **Classification Training** — SVM, Random Forest, and Decision Tree are trained on extraction %, recharge level, rainfall, and population density
3. **Regression Training** — Linear Regression and Random Forest Regressor trained on yearly temporal features to predict future extraction levels
4. **Model Persistence** — Best models saved as `.pkl` files via joblib; metrics stored in `training_summary.json`
5. **Inference** — Models loaded on-demand per API call for zero cold-start overhead

---

## Setup and Running

### Prerequisites
- Python 3.9+
- Node.js 18+
- MongoDB 6.0+
- HuggingFace API token (HF_TOKEN) for AI chat features

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017/` |
| `HF_TOKEN` | HuggingFace API Token | *Required* |

### Backend Setup
```bash
cd Backend
pip install -r requirements.txt

# Ingest data into MongoDB
python ingest_data.py

# (Optional) Re-train ML models
python -m ml.train

# Start server
uvicorn main:app --host localhost --port 8000
```

### Frontend
```bash
cd Frontend
npm install
npm run dev
```

---

## Dataset

- **india_groundwater_2022.csv** — Block-level groundwater extraction data from CGWB 2022 assessment. Columns: State, District, Block/Taluka, Stage of Ground Water Extraction (%), Category
- **india_groundwater_trends.csv** — State-level historical extraction trends for 2017, 2020, and 2022

---

## Database Migration (SQLite to MongoDB)

If you have an existing `ingres.db` and wish to migrate your data to MongoDB, run:
```bash
cd Backend
python migrate_to_mongodb.py
```
Ensure your MongoDB instance is running and your `MONGODB_URI` is correctly set.

---

## Future Improvements

1. Real-time data integration — Connect to CGWB live data feeds
2. District-level regression — Per-district time-series models using more historical years
3. Satellite data fusion — Incorporate GRACE satellite groundwater anomaly data
4. Alert system — Automated notifications for critical threshold breaches
5. Mobile application — React Native port for field workers
6. Rainfall forecasting — Integrate IMD rainfall prediction for better extraction forecasts
7. Multi-language support — Hindi and regional Indian language interfaces

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend Framework | FastAPI + Uvicorn |
| AI/LLM | Meta Llama 3 8B via HuggingFace Inference API |
| Semantic Search | sentence-transformers/all-mpnet-base-v2 |
| ML Models | scikit-learn (SVM, Random Forest, Decision Tree, Linear Regression) |
| Database | MongoDB |
| Frontend | React 19 + Vite (rolldown-vite) |
| Charts | Chart.js, react-chartjs-2, recharts |
| Map | @react-map/india |
| Styling | Custom CSS with CSS variables |
