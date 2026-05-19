import numpy as np
import os
import joblib
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
FEATURE_COLS = ["year", "rainfall_mm", "recharge_level", "population_density"]
TARGET_COL = "extraction_pct"


def train_regressors(df):
    os.makedirs(MODELS_DIR, exist_ok=True)

    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    results = {}

    lr_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", Ridge(alpha=1.0)),
    ])
    lr_pipeline.fit(X_train, y_train)
    lr_preds = lr_pipeline.predict(X_test)
    lr_rmse = float(np.sqrt(mean_squared_error(y_test, lr_preds)))
    lr_r2 = float(r2_score(y_test, lr_preds))
    results["linear_regression"] = {
        "model": lr_pipeline,
        "rmse": round(lr_rmse, 3),
        "r2": round(lr_r2, 4),
    }
    joblib.dump(lr_pipeline, os.path.join(MODELS_DIR, "lr_regressor.pkl"))

    rf_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)),
    ])
    rf_pipeline.fit(X_train, y_train)
    rf_preds = rf_pipeline.predict(X_test)
    rf_rmse = float(np.sqrt(mean_squared_error(y_test, rf_preds)))
    rf_r2 = float(r2_score(y_test, rf_preds))
    feature_importances = dict(zip(
        FEATURE_COLS,
        [round(v * 100, 2) for v in rf_pipeline.named_steps["rf"].feature_importances_]
    ))
    results["random_forest"] = {
        "model": rf_pipeline,
        "rmse": round(rf_rmse, 3),
        "r2": round(rf_r2, 4),
        "feature_importances": feature_importances,
    }
    joblib.dump(rf_pipeline, os.path.join(MODELS_DIR, "rf_regressor.pkl"))

    best_name = min(["linear_regression", "random_forest"], key=lambda k: results[k]["rmse"])
    joblib.dump(results[best_name]["model"], os.path.join(MODELS_DIR, "best_regressor.pkl"))

    summary = {
        k: {"rmse": results[k]["rmse"], "r2": results[k]["r2"]}
        for k in results
    }
    summary["best_model"] = best_name
    if "feature_importances" in results["random_forest"]:
        summary["feature_importances"] = results["random_forest"]["feature_importances"]

    return summary


def load_best_regressor():
    path = os.path.join(MODELS_DIR, "best_regressor.pkl")
    if os.path.exists(path):
        return joblib.load(path)
    return None


def predict_extraction(features: dict):
    model = load_best_regressor()
    if model is None:
        return None
    X = np.array([[
        features.get("year", 2025),
        features.get("rainfall_mm", 800),
        features.get("recharge_level", 200),
        features.get("population_density", 400),
    ]])
    predicted = float(model.predict(X)[0])
    predicted = max(5.0, min(250.0, predicted))
    return round(predicted, 2)


def predict_trend(state_name: str, years: list, base_features: dict):
    model = load_best_regressor()
    if model is None:
        return []
    results = []
    rainfall = base_features.get("rainfall_mm", 800)
    pop_density = base_features.get("population_density", 400)
    recharge = base_features.get("recharge_level", rainfall * 0.25)
    for year in years:
        pop_growth_factor = 1 + 0.012 * (year - 2022)
        X = np.array([[year, rainfall * np.random.uniform(0.95, 1.05),
                       recharge * np.random.uniform(0.95, 1.05),
                       pop_density * pop_growth_factor]])
        predicted = float(model.predict(X)[0])
        predicted = max(5.0, min(250.0, predicted))
        results.append({"year": year, "predicted_extraction": round(predicted, 2)})
    return results
