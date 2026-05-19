import numpy as np
import pandas as pd
import sqlite3
import os
import random

CATEGORY_MAP = {
    "safe": 0,
    "semi-critical": 1,
    "critical": 2,
    "over-exploited": 3,
}

CATEGORY_LABELS = ["Safe", "Semi-Critical", "Critical", "Over-Exploited"]

STATE_RAINFALL = {
    "maharashtra": 900, "karnataka": 750, "rajasthan": 300, "punjab": 450,
    "haryana": 480, "gujarat": 550, "uttar pradesh": 820, "madhya pradesh": 1100,
    "andhra pradesh": 860, "telangana": 780, "bihar": 1150, "west bengal": 1580,
    "odisha": 1450, "assam": 2900, "himachal pradesh": 1250, "uttarakhand": 1900,
    "jharkhand": 1300, "chhattisgarh": 1300, "kerala": 3000, "tamil nadu": 950,
    "delhi": 600, "goa": 2900, "tripura": 2000, "manipur": 1900,
    "meghalaya": 2950, "arunachal pradesh": 2200, "nagaland": 1800, "mizoram": 2150,
    "sikkim": 2900, "puducherry": 1200,
}

STATE_POPULATION_DENSITY = {
    "maharashtra": 365, "karnataka": 319, "rajasthan": 200, "punjab": 550,
    "haryana": 573, "gujarat": 308, "uttar pradesh": 828, "madhya pradesh": 236,
    "andhra pradesh": 308, "telangana": 312, "bihar": 1102, "west bengal": 1028,
    "odisha": 269, "assam": 397, "himachal pradesh": 123, "uttarakhand": 189,
    "jharkhand": 414, "chhattisgarh": 189, "kerala": 860, "tamil nadu": 555,
    "delhi": 11320, "goa": 394, "tripura": 350, "manipur": 122,
    "meghalaya": 132, "arunachal pradesh": 17, "nagaland": 119, "mizoram": 52,
    "sikkim": 86, "puducherry": 2598,
}


def extraction_to_category(extraction):
    if extraction < 70:
        return "safe"
    elif extraction < 90:
        return "semi-critical"
    elif extraction < 100:
        return "critical"
    else:
        return "over-exploited"


def load_existing_data():
    db_path = os.path.join(os.path.dirname(__file__), "..", "ingres.db")
    if not os.path.exists(db_path):
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql("SELECT * FROM assessments", conn)
        return df
    except Exception:
        return pd.DataFrame()


def generate_training_dataset(n_samples=6000, seed=42):
    np.random.seed(seed)
    random.seed(seed)

    existing = load_existing_data()
    rows = []

    if not existing.empty:
        for _, row in existing.iterrows():
            state = str(row.get("state", "")).lower().strip()
            extraction = float(row.get("extraction", 50))
            rainfall = STATE_RAINFALL.get(state, 800) * np.random.uniform(0.8, 1.2)
            pop_density = STATE_POPULATION_DENSITY.get(state, 400) * np.random.uniform(0.9, 1.1)
            recharge = rainfall * np.random.uniform(0.15, 0.35)
            category_str = extraction_to_category(extraction)
            rows.append({
                "extraction_pct": round(extraction, 2),
                "recharge_level": round(recharge, 2),
                "rainfall_mm": round(rainfall, 2),
                "population_density": round(pop_density, 2),
                "category": category_str,
                "category_label": CATEGORY_MAP[category_str],
            })

    remaining = n_samples - len(rows)
    if remaining > 0:
        category_targets = {
            "safe": int(remaining * 0.35),
            "semi-critical": int(remaining * 0.25),
            "critical": int(remaining * 0.15),
            "over-exploited": int(remaining * 0.25),
        }
        for cat, count in category_targets.items():
            for _ in range(count):
                if cat == "safe":
                    extraction = np.random.uniform(10, 69.9)
                elif cat == "semi-critical":
                    extraction = np.random.uniform(70, 89.9)
                elif cat == "critical":
                    extraction = np.random.uniform(90, 99.9)
                else:
                    extraction = np.random.uniform(100, 200)

                state = random.choice(list(STATE_RAINFALL.keys()))
                rainfall = STATE_RAINFALL[state] * np.random.uniform(0.6, 1.4)
                pop_density = STATE_POPULATION_DENSITY[state] * np.random.uniform(0.7, 1.3)
                recharge = rainfall * np.random.uniform(0.1, 0.4)
                rows.append({
                    "extraction_pct": round(extraction, 2),
                    "recharge_level": round(recharge, 2),
                    "rainfall_mm": round(rainfall, 2),
                    "population_density": round(pop_density, 2),
                    "category": cat,
                    "category_label": CATEGORY_MAP[cat],
                })

    df = pd.DataFrame(rows)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    return df


def generate_trend_dataset(n_per_state=8, seed=42):
    np.random.seed(seed)
    rows = []
    years = list(range(2010, 2025))

    db_path = os.path.join(os.path.dirname(__file__), "..", "ingres.db")
    anchor_data = {}
    if os.path.exists(db_path):
        try:
            with sqlite3.connect(db_path) as conn:
                trends = pd.read_sql("SELECT * FROM state_trends", conn)
            for _, row in trends.iterrows():
                state = str(row.get("State", "")).lower().strip()
                anchor_data[state] = {
                    2017: float(row.get("2017", 70)),
                    2020: float(row.get("2020", 70)),
                    2022: float(row.get("2022", 70)),
                }
        except Exception:
            pass

    for state in STATE_RAINFALL.keys():
        base_2017 = anchor_data.get(state, {}).get(2017, np.random.uniform(40, 130))
        base_2022 = anchor_data.get(state, {}).get(2022, base_2017 * np.random.uniform(0.9, 1.1))
        annual_change = (base_2022 - base_2017) / 5

        for year in years:
            extraction = base_2017 + annual_change * (year - 2017) + np.random.uniform(-5, 5)
            extraction = max(10, min(200, extraction))
            rainfall = STATE_RAINFALL[state] * np.random.uniform(0.7, 1.3)
            pop_density = STATE_POPULATION_DENSITY[state] * (1 + 0.012 * (year - 2017))
            recharge = rainfall * np.random.uniform(0.12, 0.38)
            rows.append({
                "state": state,
                "year": year,
                "extraction_pct": round(extraction, 2),
                "recharge_level": round(recharge, 2),
                "rainfall_mm": round(rainfall, 2),
                "population_density": round(pop_density, 2),
            })

    return pd.DataFrame(rows)
