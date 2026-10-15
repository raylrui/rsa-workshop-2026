#!/usr/bin/env python3
"""
Bias audit for diabetic/data/diabetic_readmission.csv
Checks representation, outcomes, and missing-data disparities
across demographic groups (race, gender, age).
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

DATA_PATH = "diabetic/data/diabetic_readmission.csv"
CHARTS_DIR = "charts"

# ── helpers ──────────────────────────────────────────────────────────────────

def readmission_rate(series):
    return (series != "no").mean()


def flag(rate, overall, threshold=0.05):
    diff = rate - overall
    if diff > threshold:
        return f"▲ +{diff*100:.1f} pp"
    elif diff < -threshold:
        return f"▼ {diff*100:.1f} pp"
    return "ok"


# ── load ─────────────────────────────────────────────────────────────────────

df = pd.read_csv(DATA_PATH)
overall_rate = readmission_rate(df["readmitted"])
N = len(df)

# Age labels (midpoints → decade labels for display)
age_label = {5: "<10", 15: "10–19", 25: "20–29", 35: "30–39",
             45: "40–49", 55: "50–59", 65: "60–69",
             75: "70–79", 85: "80–89", 95: "90+"}
df["age_label"] = df["age"].map(age_label)

# Mark lab values encoded as 'none' as missing
df["glu_missing"] = (df["max_glu_serum"] == "none").astype(int)
df["a1c_missing"] = (df["a1c_result"] == "none").astype(int)

print(f"Dataset: {N:,} records, {df.shape[1]} columns")
print(f"Overall readmission rate: {overall_rate*100:.1f}%\n")

# ═══════════════════════════════════════════════════════════════════════════
# CHECK 1 — Representation
# ═══════════════════════════════════════════════════════════════════════════

rep_race = df["race"].value_counts().rename_axis("group").reset_index(name="count")
rep_race["pct"] = rep_race["count"] / N

rep_gender = df["gender"].value_counts().rename_axis("group").reset_index(name="count")
rep_gender["pct"] = rep_gender["count"] / N

age_order = [age_label[k] for k in sorted(age_label)]
rep_age = (df["age_label"]
           .value_counts()
           .reindex(age_order)
           .rename_axis("group")
           .reset_index(name="count"))
rep_age["pct"] = rep_age["count"] / N

# Chart 1a — race representation
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
fig.suptitle("Check 1 — Group Representation", fontsize=14, fontweight="bold")

axes[0].barh(rep_race["group"], rep_race["pct"] * 100, color="steelblue", edgecolor="black", alpha=0.8)
axes[0].set_xlabel("% of dataset")
axes[0].set_title("By Race")
for i, (p, n) in enumerate(zip(rep_race["pct"], rep_race["count"])):
    axes[0].text(p * 100 + 0.3, i, f"{p*100:.1f}% (n={n:,})", va="center", fontsize=8)
axes[0].set_xlim(0, 90)

axes[1].barh(rep_gender["group"], rep_gender["pct"] * 100, color="seagreen", edgecolor="black", alpha=0.8)
axes[1].set_xlabel("% of dataset")
axes[1].set_title("By Gender")
for i, (p, n) in enumerate(zip(rep_gender["pct"], rep_gender["count"])):
    axes[1].text(p * 100 + 0.3, i, f"{p*100:.1f}% (n={n:,})", va="center", fontsize=8)
axes[1].set_xlim(0, 65)

axes[2].barh(rep_age["group"], rep_age["pct"] * 100, color="darkorange", edgecolor="black", alpha=0.8)
axes[2].set_xlabel("% of dataset")
axes[2].set_title("By Age Group")
for i, (p, n) in enumerate(zip(rep_age["pct"], rep_age["count"])):
    axes[2].text(p * 100 + 0.1, i, f"{p*100:.1f}%", va="center", fontsize=8)
axes[2].set_xlim(0, 32)

plt.tight_layout()
plt.savefig(f"{CHARTS_DIR}/bias_01_representation.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved bias_01_representation.png")

# ═══════════════════════════════════════════════════════════════════════════
# CHECK 2 — Outcome disparities
# ═══════════════════════════════════════════════════════════════════════════

def outcome_table(df, col, order=None):
    tbl = df.groupby(col)["readmitted"].apply(readmission_rate).rename("rate").reset_index()
    tbl["count"] = df.groupby(col)["readmitted"].count().values
    tbl["diff_pp"] = (tbl["rate"] - overall_rate) * 100
    tbl["flag"] = tbl["rate"].apply(lambda r: flag(r, overall_rate))
    if order:
        tbl[col] = pd.Categorical(tbl[col], categories=order, ordered=True)
        tbl = tbl.sort_values(col)
    return tbl

race_out = outcome_table(df, "race")
gender_out = outcome_table(df, "gender")
age_out = outcome_table(df, "age_label", order=age_order)

# Chart 2 — outcome rates with overall reference line
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
fig.suptitle("Check 2 — Readmission Rate by Demographic Group\n"
             f"(dashed line = overall {overall_rate*100:.1f}%)", fontsize=13, fontweight="bold")

color_fn = lambda diffs: ["tomato" if abs(d) > 5 else "steelblue" for d in diffs]

for ax, tbl, col, title in [
    (axes[0], race_out,   "race",       "By Race"),
    (axes[1], gender_out, "gender",     "By Gender"),
    (axes[2], age_out,    "age_label",  "By Age Group"),
]:
    groups = tbl[col].astype(str)
    rates  = tbl["rate"] * 100
    colors = color_fn(tbl["diff_pp"])
    ax.bar(groups, rates, color=colors, edgecolor="black", alpha=0.8)
    ax.axhline(overall_rate * 100, color="black", linestyle="--", linewidth=1.2, label="Overall")
    ax.set_ylabel("Readmission rate (%)")
    ax.set_title(title)
    ax.set_ylim(0, max(rates) * 1.18)
    ax.tick_params(axis="x", rotation=30)
    for i, (r, f_) in enumerate(zip(rates, tbl["flag"])):
        ax.text(i, r + 0.5, f"{r:.1f}%", ha="center", va="bottom", fontsize=8)
    ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(f"{CHARTS_DIR}/bias_02_outcome_rates.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved bias_02_outcome_rates.png")

# Print flags
print("\n--- Outcome flags (>5 pp from overall) ---")
for tbl, label in [(race_out, "race"), (gender_out, "gender"), (age_out, "age_label")]:
    flagged = tbl[tbl["flag"] != "ok"]
    for _, row in flagged.iterrows():
        print(f"  {label}={row[label]}  rate={row['rate']*100:.1f}%  {row['flag']}")

# ═══════════════════════════════════════════════════════════════════════════
# CHECK 3 — Missing-data disparities (glucose & A1c)
# ═══════════════════════════════════════════════════════════════════════════

def missing_table(df, demo_col, order=None):
    tbl = df.groupby(demo_col)[["glu_missing", "a1c_missing"]].mean().reset_index()
    tbl.columns = [demo_col, "glu_missing_rate", "a1c_missing_rate"]
    if order:
        tbl[demo_col] = pd.Categorical(tbl[demo_col], categories=order, ordered=True)
        tbl = tbl.sort_values(demo_col)
    return tbl

race_miss  = missing_table(df, "race")
gender_miss = missing_table(df, "gender")
age_miss   = missing_table(df, "age_label", order=age_order)

fig, axes = plt.subplots(1, 3, figsize=(16, 5))
fig.suptitle("Check 3 — Missing Lab Values by Demographic Group\n"
             "(glucose & HbA1c tests recorded as 'none')", fontsize=13, fontweight="bold")

for ax, tbl, col, title in [
    (axes[0], race_miss,   "race",       "By Race"),
    (axes[1], gender_miss, "gender",     "By Gender"),
    (axes[2], age_miss,    "age_label",  "By Age Group"),
]:
    x = np.arange(len(tbl))
    w = 0.35
    groups = tbl[col].astype(str)
    ax.bar(x - w/2, tbl["glu_missing_rate"] * 100, w, label="Glucose missing",
           color="steelblue", edgecolor="black", alpha=0.8)
    ax.bar(x + w/2, tbl["a1c_missing_rate"] * 100, w, label="A1c missing",
           color="darkorange", edgecolor="black", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=30, ha="right")
    ax.set_ylabel("Missing rate (%)")
    ax.set_title(title)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(f"{CHARTS_DIR}/bias_03_missing_data.png", dpi=150, bbox_inches="tight")
plt.close()
print("Saved bias_03_missing_data.png")

# ═══════════════════════════════════════════════════════════════════════════
# Collect findings for report
# ═══════════════════════════════════════════════════════════════════════════

findings = {
    "overall_rate": overall_rate,
    "N": N,
    "race_out": race_out,
    "gender_out": gender_out,
    "age_out": age_out,
    "race_miss": race_miss,
    "gender_miss": gender_miss,
    "age_miss": age_miss,
}

print("\nAll charts saved. Generating report...")
