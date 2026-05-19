import numpy as np
import os
import joblib
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score
from sklearn.pipeline import Pipeline

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
FEATURE_COLS = ["extraction_pct", "recharge_level", "rainfall_mm", "population_density"]
TARGET_COL = "category_label"
LABEL_NAMES = ["Safe", "Semi-Critical", "Critical", "Over-Exploited"]


def train_classifiers(df):
    os.makedirs(MODELS_DIR, exist_ok=True)

    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    results = {}

    svm_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("svm", SVC(kernel="rbf", C=10, gamma="scale", probability=True, random_state=42)),
    ])
    svm_pipeline.fit(X_train, y_train)
    svm_preds = svm_pipeline.predict(X_test)
    svm_acc = accuracy_score(y_test, svm_preds)
    results["svm"] = {
        "model": svm_pipeline,
        "accuracy": round(svm_acc * 100, 2),
        "report": classification_report(y_test, svm_preds, target_names=LABEL_NAMES, output_dict=True),
    }
    joblib.dump(svm_pipeline, os.path.join(MODELS_DIR, "svm_classifier.pkl"))

    rf_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)),
    ])
    rf_pipeline.fit(X_train, y_train)
    rf_preds = rf_pipeline.predict(X_test)
    rf_acc = accuracy_score(y_test, rf_preds)
    feature_importances = dict(zip(
        FEATURE_COLS,
        [round(v * 100, 2) for v in rf_pipeline.named_steps["rf"].feature_importances_]
    ))
    results["random_forest"] = {
        "model": rf_pipeline,
        "accuracy": round(rf_acc * 100, 2),
        "report": classification_report(y_test, rf_preds, target_names=LABEL_NAMES, output_dict=True),
        "feature_importances": feature_importances,
    }
    joblib.dump(rf_pipeline, os.path.join(MODELS_DIR, "rf_classifier.pkl"))

    dt_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("dt", DecisionTreeClassifier(max_depth=8, random_state=42)),
    ])
    dt_pipeline.fit(X_train, y_train)
    dt_preds = dt_pipeline.predict(X_test)
    dt_acc = accuracy_score(y_test, dt_preds)
    results["decision_tree"] = {
        "model": dt_pipeline,
        "accuracy": round(dt_acc * 100, 2),
        "report": classification_report(y_test, dt_preds, target_names=LABEL_NAMES, output_dict=True),
    }
    joblib.dump(dt_pipeline, os.path.join(MODELS_DIR, "dt_classifier.pkl"))

    best_name = max(
        ["svm", "random_forest", "decision_tree"],
        key=lambda k: results[k]["accuracy"]
    )
    joblib.dump(results[best_name]["model"], os.path.join(MODELS_DIR, "best_classifier.pkl"))

    summary = {
        k: {"accuracy": results[k]["accuracy"]}
        for k in results
    }
    summary["best_model"] = best_name
    if "feature_importances" in results["random_forest"]:
        summary["feature_importances"] = results["random_forest"]["feature_importances"]

    return summary


def load_best_classifier():
    path = os.path.join(MODELS_DIR, "best_classifier.pkl")
    if os.path.exists(path):
        return joblib.load(path)
    return None


def predict_risk(features: dict):
    model = load_best_classifier()
    if model is None:
        return None
    X = np.array([[
        features.get("extraction_pct", 70),
        features.get("recharge_level", 200),
        features.get("rainfall_mm", 800),
        features.get("population_density", 400),
    ]])
    pred_label = int(model.predict(X)[0])
    proba = model.predict_proba(X)[0].tolist()
    return {
        "category_index": pred_label,
        "category": LABEL_NAMES[pred_label],
        "probabilities": {LABEL_NAMES[i]: round(p * 100, 1) for i, p in enumerate(proba)},
    }
