"""
INGRES ML Training Script
Run once to generate synthetic dataset and train all ML models.
Usage: python -m ml.train
"""

import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ml.dataset import generate_training_dataset, generate_trend_dataset
from ml.classifier import train_classifiers
from ml.regressor import train_regressors

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def run_training():
    print("=" * 60)
    print("INGRES ML Training Pipeline")
    print("=" * 60)

    os.makedirs(MODELS_DIR, exist_ok=True)

    print("\n[1/4] Generating classification training dataset...")
    clf_df = generate_training_dataset(n_samples=6000)
    print(f"      Dataset size: {len(clf_df)} rows")
    print(f"      Category distribution:\n{clf_df['category'].value_counts().to_string()}")

    print("\n[2/4] Training classifiers (SVM, Random Forest, Decision Tree)...")
    clf_results = train_classifiers(clf_df)
    print(f"      SVM Accuracy:           {clf_results['svm']['accuracy']}%")
    print(f"      Random Forest Accuracy: {clf_results['random_forest']['accuracy']}%")
    print(f"      Decision Tree Accuracy: {clf_results['decision_tree']['accuracy']}%")
    print(f"      Best Model:             {clf_results['best_model']}")

    print("\n[3/4] Generating regression training dataset...")
    reg_df = generate_trend_dataset()
    print(f"      Dataset size: {len(reg_df)} rows, {reg_df['state'].nunique()} states")

    print("\n[4/4] Training regressors (Linear Regression, Random Forest)...")
    reg_results = train_regressors(reg_df)
    print(f"      Linear Regression RMSE: {reg_results['linear_regression']['rmse']}  R2: {reg_results['linear_regression']['r2']}")
    print(f"      Random Forest     RMSE: {reg_results['random_forest']['rmse']}  R2: {reg_results['random_forest']['r2']}")
    print(f"      Best Model:             {reg_results['best_model']}")

    summary = {
        "classifiers": clf_results,
        "regressors": reg_results,
    }
    summary_path = os.path.join(MODELS_DIR, "training_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("Training complete. Models saved to Backend/models/")
    print("=" * 60)
    return summary


if __name__ == "__main__":
    run_training()
