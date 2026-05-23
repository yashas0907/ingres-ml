import argparse
import json
from pathlib import Path

import pandas as pd


SYSTEM = (
    "You are INGRES, an Indian groundwater intelligence assistant. "
    "Use only the supplied evidence. Be concise, practical, and do not invent numbers."
)


CAUSES = {
    "Over-Exploited": "withdrawal is higher than recharge, often from irrigation pressure and dense water demand",
    "Critical": "the region is close to full recharge usage and has little buffer for dry years",
    "Semi-Critical": "extraction is rising but has not yet crossed the critical threshold",
    "Safe": "current extraction remains below the major stress threshold",
}


def category_from_extraction(value):
    if value < 70:
        return "Safe"
    if value < 90:
        return "Semi-Critical"
    if value < 100:
        return "Critical"
    return "Over-Exploited"


def add_example(rows, user, assistant):
    rows.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    })


def build_assessment_examples(rows, assessments):
    for row in assessments.to_dict("records"):
        state = row["State"]
        district = row["District"]
        block = row["Block/Taluka"]
        extraction = round(float(row["Stage of Ground Water Extraction (%)"]), 1)
        category = row["Category"]
        cause = CAUSES.get(category, "local extraction and recharge are imbalanced")

        evidence = (
            f"Evidence: State={state}; District={district}; Block={block}; "
            f"Extraction={extraction}%; Category={category}."
        )

        add_example(
            rows,
            f"What is the groundwater status of {district} in {state}?\n{evidence}",
            (
                f"{district}, {state} is classified as {category}. "
                f"The recorded groundwater extraction stage is {extraction}%. "
                f"This indicates that {cause}. A practical next step is to monitor borewell "
                f"withdrawal and strengthen recharge planning at block level."
            ),
        )

        add_example(
            rows,
            f"Why is {block} in {district} marked {category}?\n{evidence}",
            (
                f"{block} is marked {category} because its extraction stage is {extraction}%. "
                f"In INGRES terms, that means {cause}. The answer should be treated as a "
                f"planning signal, not a complete hydrogeological diagnosis."
            ),
        )

        add_example(
            rows,
            f"Suggest groundwater action for {district}, {state}.\n{evidence}",
            (
                f"For {district}, prioritize actions that match the {category} risk level: "
                f"crop-water budgeting, recharge structures, leak reduction, and pumping discipline. "
                f"The intervention urgency is driven by the {extraction}% extraction value."
            ),
        )


def build_trend_examples(rows, trends):
    for row in trends.to_dict("records"):
        state = row["State"]
        values = {year: round(float(row[year]), 1) for year in ["2017", "2020", "2022"]}
        latest = values["2022"]
        category = category_from_extraction(latest)
        direction = "worsened" if values["2022"] > values["2017"] else "improved" if values["2022"] < values["2017"] else "stayed stable"
        evidence = f"Evidence: State={state}; 2017={values['2017']}%; 2020={values['2020']}%; 2022={values['2022']}%."

        add_example(
            rows,
            f"Explain the groundwater trend in {state}.\n{evidence}",
            (
                f"{state}'s groundwater extraction has {direction} from {values['2017']}% in 2017 "
                f"to {values['2022']}% in 2022. The latest category is {category}. "
                f"Use this as a trend signal and combine it with district-level evidence before policy action."
            ),
        )


def build_comparison_examples(rows, assessments):
    state_summary = (
        assessments
        .assign(**{"Stage of Ground Water Extraction (%)": assessments["Stage of Ground Water Extraction (%)"].astype(float)})
        .groupby("State")["Stage of Ground Water Extraction (%)"]
        .mean()
        .sort_values(ascending=False)
    )
    states = list(state_summary.index)
    for left, right in zip(states[:8], reversed(states[-8:])):
        left_val = round(float(state_summary[left]), 1)
        right_val = round(float(state_summary[right]), 1)
        left_cat = category_from_extraction(left_val)
        right_cat = category_from_extraction(right_val)
        evidence = f"Evidence: {left} average extraction={left_val}%; {right} average extraction={right_val}%."
        higher = left if left_val > right_val else right
        add_example(
            rows,
            f"Compare groundwater stress in {left} and {right}.\n{evidence}",
            (
                f"{higher} has the higher groundwater pressure in this comparison. "
                f"{left} is {left_cat} at {left_val}%, while {right} is {right_cat} at {right_val}%. "
                f"The comparison should guide prioritization, not replace local aquifer surveys."
            ),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-dir", default="Backend")
    parser.add_argument("--out", default="training/gemma_groundwater/data/ingres_gemma_sft.jsonl")
    parser.add_argument("--max-examples", type=int, default=0)
    args = parser.parse_args()

    backend = Path(args.backend_dir)
    assessments = pd.read_csv(backend / "india_groundwater_2022.csv")
    trends = pd.read_csv(backend / "india_groundwater_trends.csv")

    rows = []
    build_assessment_examples(rows, assessments)
    build_trend_examples(rows, trends)
    build_comparison_examples(rows, assessments)

    if args.max_examples > 0:
        rows = rows[:args.max_examples]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} examples to {out}")


if __name__ == "__main__":
    main()
