import os
import json
import sqlite3
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api/ml", tags=["ML"])

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ingres.db")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

CATEGORY_COLORS = {
    "Safe": "#2ecc71",
    "Semi-Critical": "#f39c12",
    "Critical": "#e67e22",
    "Over-Exploited": "#e74c3c",
}

STATE_RAINFALL = {
    "maharashtra": 900, "karnataka": 750, "rajasthan": 300, "punjab": 450,
    "haryana": 480, "gujarat": 550, "uttar pradesh": 820, "madhya pradesh": 1100,
    "andhra pradesh": 860, "telangana": 780, "bihar": 1150, "west bengal": 1580,
    "odisha": 1450, "assam": 2900, "himachal pradesh": 1250, "uttarakhand": 1900,
    "jharkhand": 1300, "chhattisgarh": 1300, "kerala": 3000, "tamil nadu": 950,
    "delhi": 600,
}

STATE_POP_DENSITY = {
    "maharashtra": 365, "karnataka": 319, "rajasthan": 200, "punjab": 550,
    "haryana": 573, "gujarat": 308, "uttar pradesh": 828, "madhya pradesh": 236,
    "andhra pradesh": 308, "telangana": 312, "bihar": 1102, "west bengal": 1028,
    "odisha": 269, "assam": 397, "himachal pradesh": 123, "uttarakhand": 189,
    "jharkhand": 414, "chhattisgarh": 189, "kerala": 860, "tamil nadu": 555,
    "delhi": 11320,
}


class RiskPredictRequest(BaseModel):
    extraction_pct: float
    recharge_level: Optional[float] = None
    rainfall_mm: Optional[float] = None
    population_density: Optional[float] = None
    state: Optional[str] = None


class ExtractionPredictRequest(BaseModel):
    year: int
    state: Optional[str] = None
    rainfall_mm: Optional[float] = None
    recharge_level: Optional[float] = None
    population_density: Optional[float] = None


class CompareRequest(BaseModel):
    locations: List[str]


def get_db_connection():
    if not os.path.exists(DB_PATH):
        alt = os.path.join(os.path.dirname(__file__), "..", "..", "ingres.db")
        if os.path.exists(alt):
            return sqlite3.connect(alt)
        return None
    return sqlite3.connect(DB_PATH)


def load_training_summary():
    path = os.path.join(MODELS_DIR, "training_summary.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


@router.post("/predict-risk")
async def predict_risk(req: RiskPredictRequest):
    from ml.classifier import predict_risk as _predict
    state_key = (req.state or "").lower().strip()
    rainfall = req.rainfall_mm if req.rainfall_mm is not None else STATE_RAINFALL.get(state_key, 800)
    pop_density = req.population_density if req.population_density is not None else STATE_POP_DENSITY.get(state_key, 400)
    recharge = req.recharge_level if req.recharge_level is not None else rainfall * 0.25

    result = _predict({
        "extraction_pct": req.extraction_pct,
        "recharge_level": recharge,
        "rainfall_mm": rainfall,
        "population_density": pop_density,
    })
    if result is None:
        return {"error": "Model not loaded. Run training first."}
    result["color"] = CATEGORY_COLORS.get(result["category"], "#888")
    result["input"] = {
        "extraction_pct": req.extraction_pct,
        "recharge_level": round(recharge, 1),
        "rainfall_mm": round(rainfall, 1),
        "population_density": round(pop_density, 1),
    }
    return result


@router.post("/predict-groundwater")
async def predict_groundwater(req: ExtractionPredictRequest):
    from ml.regressor import predict_extraction, predict_trend
    import numpy as np
    state_key = (req.state or "").lower().strip()
    rainfall = req.rainfall_mm if req.rainfall_mm is not None else STATE_RAINFALL.get(state_key, 800)
    pop_density = req.population_density if req.population_density is not None else STATE_POP_DENSITY.get(state_key, 400)
    recharge = req.recharge_level if req.recharge_level is not None else rainfall * 0.25

    predicted = predict_extraction({
        "year": req.year,
        "rainfall_mm": rainfall,
        "recharge_level": recharge,
        "population_density": pop_density,
    })
    if predicted is None:
        return {"error": "Model not loaded."}

    from ml.dataset import extraction_to_category
    from ml.classifier import LABEL_NAMES
    from ml.dataset import CATEGORY_MAP
    cat_str = extraction_to_category(predicted)
    cat_label = CATEGORY_MAP.get(cat_str, 0)

    future_years = list(range(req.year, req.year + 6))
    trend = predict_trend(state_key, future_years, {
        "rainfall_mm": rainfall,
        "population_density": pop_density,
        "recharge_level": recharge,
    })

    return {
        "predicted_extraction": predicted,
        "year": req.year,
        "category": LABEL_NAMES[cat_label],
        "color": CATEGORY_COLORS.get(LABEL_NAMES[cat_label], "#888"),
        "trend_forecast": trend,
        "inputs": {
            "rainfall_mm": round(rainfall, 1),
            "recharge_level": round(recharge, 1),
            "population_density": round(pop_density, 1),
        }
    }


@router.get("/top-risk-districts")
async def top_risk_districts(limit: int = 15):
    conn = get_db_connection()
    if conn is None:
        return {"districts": []}
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(assessments)")
        cols = [info[1] for info in cursor.fetchall()]
        state_col = next((c for c in cols if "state" in c.lower()), "state")
        dist_col = next((c for c in cols if "district" in c.lower()), "district_name")
        extr_col = next((c for c in cols if "extract" in c.lower()), "extraction")
        cat_col = next((c for c in cols if "categor" in c.lower()), "category")
        cursor.execute(
            f'SELECT "{state_col}", "{dist_col}", "{extr_col}", "{cat_col}" '
            f'FROM assessments ORDER BY CAST("{extr_col}" AS REAL) DESC LIMIT ?',
            (limit,)
        )
        rows = cursor.fetchall()
        return {
            "districts": [
                {
                    "state": r[0], "district": r[1],
                    "extraction": round(float(r[2]), 1),
                    "category": r[3],
                    "color": CATEGORY_COLORS.get(str(r[3]).strip().title(), "#e74c3c")
                }
                for r in rows if r[2] is not None
            ]
        }
    finally:
        conn.close()


@router.get("/district-distribution")
async def district_distribution():
    conn = get_db_connection()
    if conn is None:
        return {"distribution": []}
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(assessments)")
        cols = [info[1] for info in cursor.fetchall()]
        cat_col = next((c for c in cols if "categor" in c.lower()), "category")
        cursor.execute(
            f'SELECT "{cat_col}", COUNT(*) as cnt FROM assessments GROUP BY "{cat_col}"'
        )
        rows = cursor.fetchall()
        total = sum(r[1] for r in rows)
        return {
            "distribution": [
                {
                    "category": r[0],
                    "count": r[1],
                    "percentage": round(r[1] / total * 100, 1) if total else 0,
                    "color": CATEGORY_COLORS.get(str(r[0]).strip().title(), "#888")
                }
                for r in rows if r[0]
            ]
        }
    finally:
        conn.close()


@router.get("/trend-analysis")
async def trend_analysis():
    conn = get_db_connection()
    if conn is None:
        return {"trends": []}
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(state_trends)")
        cols_info = cursor.fetchall()
        if not cols_info:
            return {"trends": []}
        cols = [info[1] for info in cols_info]
        state_col = cols[0]
        year_cols = [c for c in cols if c != state_col]
        cursor.execute(f'SELECT * FROM state_trends')
        rows = cursor.fetchall()
        result = []
        for row in rows:
            state = row[0]
            values = []
            for i, yc in enumerate(year_cols):
                try:
                    values.append({"year": int(yc), "extraction": round(float(row[i + 1]), 1)})
                except Exception:
                    pass
            if values:
                last_val = values[-1]["extraction"] if values else 0
                cat = "safe" if last_val < 70 else "semi-critical" if last_val < 90 else "critical" if last_val < 100 else "over-exploited"
                result.append({
                    "state": state,
                    "values": values,
                    "latest_extraction": last_val,
                    "category": cat.replace("-", " ").title(),
                    "color": CATEGORY_COLORS.get(cat.replace("-", " ").title(), "#888"),
                })
        result.sort(key=lambda x: x["latest_extraction"], reverse=True)
        return {"trends": result, "years": [int(y) for y in year_cols]}
    finally:
        conn.close()


@router.post("/compare-districts")
async def compare_districts(req: CompareRequest):
    conn = get_db_connection()
    if conn is None:
        return {"comparison": []}
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(assessments)")
        cols = [info[1] for info in cursor.fetchall()]
        state_col = next((c for c in cols if "state" in c.lower()), "state")
        dist_col = next((c for c in cols if "district" in c.lower()), "district_name")
        extr_col = next((c for c in cols if "extract" in c.lower()), "extraction")
        cat_col = next((c for c in cols if "categor" in c.lower()), "category")

        results = []
        for loc in req.locations:
            loc_lower = loc.lower().strip()
            cursor.execute(
                f'SELECT "{state_col}", "{dist_col}", AVG(CAST("{extr_col}" AS REAL)), "{cat_col}" '
                f'FROM assessments WHERE LOWER("{state_col}") = ? OR LOWER("{dist_col}") = ? '
                f'GROUP BY "{state_col}", "{dist_col}" LIMIT 1',
                (loc_lower, loc_lower)
            )
            row = cursor.fetchone()
            if row:
                extr = round(float(row[2]), 1)
                cat = str(row[3]).strip()
                results.append({
                    "name": row[1].title() if row[1] else row[0].title(),
                    "state": row[0],
                    "extraction": extr,
                    "category": cat,
                    "color": CATEGORY_COLORS.get(cat.title(), "#888"),
                    "recharge_estimate": round(extr * 0.7, 1),
                })
        return {"comparison": results}
    finally:
        conn.close()


@router.get("/model-stats")
async def model_stats():
    summary = load_training_summary()
    if not summary:
        return {"error": "No training summary found. Run training first."}
    return {
        "classifiers": {
            "svm": summary.get("classifiers", {}).get("svm", {}),
            "random_forest": summary.get("classifiers", {}).get("random_forest", {}),
            "decision_tree": summary.get("classifiers", {}).get("decision_tree", {}),
            "best_model": summary.get("classifiers", {}).get("best_model", ""),
            "feature_importances": summary.get("classifiers", {}).get("feature_importances", {}),
        },
        "regressors": {
            "linear_regression": summary.get("regressors", {}).get("linear_regression", {}),
            "random_forest": summary.get("regressors", {}).get("random_forest", {}),
            "best_model": summary.get("regressors", {}).get("best_model", ""),
            "feature_importances": summary.get("regressors", {}).get("feature_importances", {}),
        }
    }


@router.get("/overview-stats")
async def overview_stats():
    conn = get_db_connection()
    if conn is None:
        return {}
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(assessments)")
        cols = [info[1] for info in cursor.fetchall()]
        state_col = next((c for c in cols if "state" in c.lower()), "state")
        extr_col = next((c for c in cols if "extract" in c.lower()), "extraction")
        cat_col = next((c for c in cols if "categor" in c.lower()), "category")

        cursor.execute(f'SELECT COUNT(*) FROM assessments')
        total_blocks = cursor.fetchone()[0]

        cursor.execute(f'SELECT COUNT(DISTINCT "{state_col}") FROM assessments')
        total_states = cursor.fetchone()[0]

        cursor.execute(
            f'SELECT COUNT(*) FROM assessments WHERE LOWER("{cat_col}") = ?',
            ("over-exploited",)
        )
        over_exploited = cursor.fetchone()[0]

        cursor.execute(
            f'SELECT AVG(CAST("{extr_col}" AS REAL)) FROM assessments'
        )
        avg_extraction = cursor.fetchone()[0]

        cursor.execute(
            f'SELECT COUNT(*) FROM assessments WHERE LOWER("{cat_col}") = ?',
            ("safe",)
        )
        safe_count = cursor.fetchone()[0]

        return {
            "total_blocks": total_blocks,
            "total_states": total_states,
            "over_exploited_blocks": over_exploited,
            "safe_blocks": safe_count,
            "avg_extraction": round(float(avg_extraction or 0), 1),
            "over_exploited_pct": round(over_exploited / total_blocks * 100, 1) if total_blocks else 0,
        }
    finally:
        conn.close()
