import os
import json
import motor.motor_asyncio
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api/ml", tags=["ML"])

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "ingres_db"
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


def get_db(request: Request):
    return request.app.state.db


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
async def top_risk_districts(request: Request, limit: int = 15):
    db = get_db(request)
    assessments_coll = db.assessments
    sample = await assessments_coll.find_one()
    if not sample:
        return {"districts": []}

    cols = list(sample.keys())
    state_col = next((c for c in cols if "state" in c.lower()), "state")
    dist_col = next((c for c in cols if "district" in c.lower()), "district_name")
    extr_col = next((c for c in cols if "extract" in c.lower()), "extraction")
    cat_col = next((c for c in cols if "categor" in c.lower()), "category")

    cursor = assessments_coll.find().sort(extr_col, -1).limit(limit)
    rows = await cursor.to_list(length=limit)

    return {
        "districts": [
            {
                "state": r.get(state_col),
                "district": r.get(dist_col),
                "extraction": round(float(r.get(extr_col, 0)), 1),
                "category": r.get(cat_col),
                "color": CATEGORY_COLORS.get(str(r.get(cat_col)).strip().title(), "#e74c3c")
            }
            for r in rows if r.get(extr_col) is not None
        ]
    }


@router.get("/district-distribution")
async def district_distribution(request: Request):
    db = get_db(request)
    assessments_coll = db.assessments
    sample = await assessments_coll.find_one()
    if not sample:
        return {"distribution": []}

    cols = list(sample.keys())
    cat_col = next((c for c in cols if "categor" in c.lower()), "category")

    pipeline = [
        {"$group": {"_id": f"${cat_col}", "cnt": {"$sum": 1}}}
    ]
    rows = await assessments_coll.aggregate(pipeline).to_list(length=None)
    total = sum(r["cnt"] for r in rows)

    return {
        "distribution": [
            {
                "category": r["_id"],
                "count": r["cnt"],
                "percentage": round(r["cnt"] / total * 100, 1) if total else 0,
                "color": CATEGORY_COLORS.get(str(r["_id"]).strip().title(), "#888")
            }
            for r in rows if r["_id"]
        ]
    }


@router.get("/trend-analysis")
async def trend_analysis(request: Request):
    db = get_db(request)
    state_trends_coll = db.state_trends

    rows = await state_trends_coll.find().to_list(length=None)
    if not rows:
        return {"trends": []}

    sample = rows[0]
    cols = list(sample.keys())
    state_col = next((c for c in cols if "state" in c.lower()), "State")
    year_cols = [c for c in cols if c.isdigit()]
    year_cols.sort()

    result = []
    for row in rows:
        state = row.get(state_col)
        values = []
        for yc in year_cols:
            try:
                values.append({"year": int(yc), "extraction": round(float(row.get(yc, 0)), 1)})
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


@router.post("/compare-districts")
async def compare_districts(request: Request, req: CompareRequest):
    db = get_db(request)
    assessments_coll = db.assessments
    sample = await assessments_coll.find_one()
    if not sample:
        return {"comparison": []}

    cols = list(sample.keys())
    state_col = next((c for c in cols if "state" in c.lower()), "state")
    dist_col = next((c for c in cols if "district" in c.lower()), "district_name")
    extr_col = next((c for c in cols if "extract" in c.lower()), "extraction")
    cat_col = next((c for c in cols if "categor" in c.lower()), "category")

    results = []
    for loc in req.locations:
        loc_lower = loc.lower().strip()

        pipeline = [
            {"$match": {"$or": [{state_col: {"$regex": f"^{loc}$", "$options": "i"}}, {dist_col: {"$regex": f"^{loc}$", "$options": "i"}}]}},
            {"$group": {
                "_id": { "state": f"${state_col}", "district": f"${dist_col}" },
                "avg_extraction": {"$avg": f"${extr_col}"},
                "category": {"$first": f"${cat_col}"}
            }},
            {"$limit": 1}
        ]

        agg_res = await assessments_coll.aggregate(pipeline).to_list(1)
        if agg_res:
            row = agg_res[0]
            extr = round(float(row["avg_extraction"]), 1)
            cat = str(row["category"]).strip()
            results.append({
                "name": row["_id"]["district"].title() if row["_id"]["district"] else row["_id"]["state"].title(),
                "state": row["_id"]["state"],
                "extraction": extr,
                "category": cat,
                "color": CATEGORY_COLORS.get(cat.title(), "#888"),
                "recharge_estimate": round(extr * 0.7, 1),
            })
    return {"comparison": results}


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
async def overview_stats(request: Request):
    db = get_db(request)
    assessments_coll = db.assessments
    sample = await assessments_coll.find_one()
    if not sample:
        return {}

    cols = list(sample.keys())
    state_col = next((c for c in cols if "state" in c.lower()), "state")
    extr_col = next((c for c in cols if "extract" in c.lower()), "extraction")
    cat_col = next((c for c in cols if "categor" in c.lower()), "category")

    total_blocks = await assessments_coll.count_documents({})

    total_states_res = await assessments_coll.distinct(state_col)
    total_states = len(total_states_res)

    over_exploited = await assessments_coll.count_documents({cat_col: {"$regex": "^over-exploited$", "$options": "i"}})

    pipeline = [
        {"$group": {"_id": None, "avg_extraction": {"$avg": f"${extr_col}"}}}
    ]
    agg_res = await assessments_coll.aggregate(pipeline).to_list(1)
    avg_extraction = agg_res[0]["avg_extraction"] if agg_res else 0

    safe_count = await assessments_coll.count_documents({cat_col: {"$regex": "^safe$", "$options": "i"}})

    return {
        "total_blocks": total_blocks,
        "total_states": total_states,
        "over_exploited_blocks": over_exploited,
        "safe_blocks": safe_count,
        "avg_extraction": round(float(avg_extraction or 0), 1),
        "over_exploited_pct": round(over_exploited / total_blocks * 100, 1) if total_blocks else 0,
    }
