"""
Diabetic Transformed Dataset Visualization
Generates exploratory charts and saves them as PNG files in charts/.
Source: diabetic/data/diabetic_transformed.csv
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import numpy as np

# ── Configuration ─────────────────────────────────────────────────────────────
DATA_PATH  = "diabetic/data/diabetic_transformed.csv"
CHARTS_DIR = "charts"
TARGET_COL = "readmitted"
PREFIX     = "t"   # prefix to distinguish from prior chart set

os.makedirs(CHARTS_DIR, exist_ok=True)
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({"figure.dpi": 150, "savefig.bbox": "tight"})

df = pd.read_csv(DATA_PATH)
print(f"Loaded {len(df):,} rows × {df.shape[1]} columns")

# ── Age label mapping (decade midpoints → readable labels) ───────────────────
age_label = {5: "<10", 15: "10–19", 25: "20–29", 35: "30–39",
             45: "40–49", 55: "50–59", 65: "60–69",
             75: "70–79", 85: "80–89", 95: "90+"}
df["age_group"] = df["age"].map(age_label)
age_order = [age_label[k] for k in sorted(age_label)]

# Reconstruct race from one-hot columns
race_cols = ["race_caucasian", "race_african_american", "race_hispanic",
             "race_other", "race_asian"]
df["race"] = df[race_cols].idxmax(axis=1).str.replace("race_", "").str.replace("_", " ").str.title()

# Target palette
TARGET_VALS = df[TARGET_COL].unique().tolist()
palette = {"no": "#4C72B0", ">30": "#DD8452", "<30": "#55A868"}

saved = []

def save(name: str):
    path = os.path.join(CHARTS_DIR, name)
    plt.savefig(path)
    plt.close()
    saved.append(name)
    print(f"  ✔  {name}")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t01 — Target distribution (pie + bar)
# ════════════════════════════════════════════════════════════════════════════════
counts = df[TARGET_COL].value_counts().reindex(["no", ">30", "<30"])
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Readmission Class Distribution", fontsize=14, fontweight="bold")

colors = [palette[v] for v in counts.index]
ax1.pie(counts, labels=counts.index, autopct="%1.1f%%", colors=colors,
        startangle=140, wedgeprops={"edgecolor": "white", "linewidth": 1.5})
ax1.set_title("Proportion")

ax2.bar(counts.index, counts.values, color=colors, edgecolor="black", alpha=0.85)
ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax2.set_ylabel("Count")
ax2.set_title("Absolute counts")
for i, (label, val) in enumerate(zip(counts.index, counts.values)):
    ax2.text(i, val + 200, f"{val:,}", ha="center", fontsize=10)

plt.tight_layout()
save(f"{PREFIX}01_target_distribution.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t02 — Readmission rate by age group (% stacked bar)
# ════════════════════════════════════════════════════════════════════════════════
grp = (df.groupby(["age_group", TARGET_COL])
         .size()
         .reset_index(name="count"))
grp["age_group"] = pd.Categorical(grp["age_group"], categories=age_order, ordered=True)
grp = grp.sort_values("age_group")
grp["pct"] = grp["count"] / grp.groupby("age_group")["count"].transform("sum") * 100

pivot = grp.pivot(index="age_group", columns=TARGET_COL, values="pct").fillna(0)
pivot = pivot.reindex(columns=["no", ">30", "<30"])

fig, ax = plt.subplots(figsize=(12, 6))
bottom = np.zeros(len(pivot))
for col in pivot.columns:
    bars = ax.bar(pivot.index, pivot[col], bottom=bottom,
                  label=col, color=palette[col], edgecolor="white", alpha=0.9)
    bottom += pivot[col].values

ax.set_xlabel("Age Group", fontsize=11)
ax.set_ylabel("% of patients", fontsize=11)
ax.set_title("Readmission Outcome Distribution by Age Group", fontsize=13, fontweight="bold")
ax.tick_params(axis="x", rotation=30)
ax.legend(title="Readmitted", bbox_to_anchor=(1.01, 1), loc="upper left")
ax.set_ylim(0, 105)
plt.tight_layout()
save(f"{PREFIX}02_readmission_by_age.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t03 — Readmission rate by race (grouped % bar)
# ════════════════════════════════════════════════════════════════════════════════
grp = (df.groupby(["race", TARGET_COL])
         .size()
         .reset_index(name="count"))
grp["pct"] = grp["count"] / grp.groupby("race")["count"].transform("sum") * 100

pivot = grp.pivot(index="race", columns=TARGET_COL, values="pct").fillna(0)
pivot = pivot.reindex(columns=["no", ">30", "<30"])
pivot = pivot.sort_values("no")

fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(pivot))
w = 0.25
for i, col in enumerate(pivot.columns):
    ax.bar(x + (i - 1) * w, pivot[col], w,
           label=col, color=palette[col], edgecolor="black", alpha=0.85)

ax.set_xticks(x)
ax.set_xticklabels(pivot.index, rotation=20, ha="right")
ax.set_ylabel("% within race group")
ax.set_title("Readmission Outcome by Race", fontsize=13, fontweight="bold")
ax.legend(title="Readmitted")
plt.tight_layout()
save(f"{PREFIX}03_readmission_by_race.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t04 — Binary feature rates by readmission class
# ════════════════════════════════════════════════════════════════════════════════
binary_cols = ["change", "diabetes_med"]
labels = {"change": "Medication Change", "diabetes_med": "On Diabetes Medication"}

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Binary Feature Rates by Readmission Class", fontsize=13, fontweight="bold")

for ax, col in zip(axes, binary_cols):
    rates = df.groupby(TARGET_COL)[col].mean() * 100
    rates = rates.reindex(["no", ">30", "<30"])
    colors = [palette[v] for v in rates.index]
    ax.bar(rates.index, rates.values, color=colors, edgecolor="black", alpha=0.85)
    ax.set_ylabel("% of patients (Yes)")
    ax.set_title(labels[col])
    ax.set_ylim(0, 100)
    for i, val in enumerate(rates.values):
        ax.text(i, val + 1.5, f"{val:.1f}%", ha="center", fontsize=10)

plt.tight_layout()
save(f"{PREFIX}04_binary_features_by_readmission.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t05 — Numeric distributions: time in hospital & lab procedures (histogram)
# ════════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Numeric Feature Distributions by Readmission Class", fontsize=13, fontweight="bold")

for ax, col, title in [
    (axes[0], "time_in_hospital", "Time in Hospital (days)"),
    (axes[1], "num_lab_procedures", "Number of Lab Procedures"),
]:
    for val in ["no", ">30", "<30"]:
        subset = df[df[TARGET_COL] == val][col]
        ax.hist(subset, bins=25, alpha=0.55, label=val, color=palette[val], edgecolor="none")
    ax.set_xlabel(title)
    ax.set_ylabel("Count")
    ax.set_title(title)
    ax.legend(title="Readmitted")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

plt.tight_layout()
save(f"{PREFIX}05_numeric_histograms.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t06 — Box plots: medications & diagnoses by readmission
# ════════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 6))
fig.suptitle("Medications & Diagnoses by Readmission Class", fontsize=13, fontweight="bold")

order = ["no", ">30", "<30"]
for ax, col, title in [
    (axes[0], "num_medications", "Number of Medications"),
    (axes[1], "number_diagnoses", "Number of Diagnoses"),
]:
    sns.boxplot(data=df, x=TARGET_COL, y=col, order=order,
                hue=TARGET_COL, palette=palette, legend=False, ax=ax)
    ax.set_xlabel("Readmitted")
    ax.set_ylabel(title)
    ax.set_title(title)

plt.tight_layout()
save(f"{PREFIX}06_boxplots_meds_diagnoses.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t07 — KDE: inpatient & emergency visits
# ════════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("KDE — Prior Visit Counts by Readmission Class", fontsize=13, fontweight="bold")

for ax, col, title in [
    (axes[0], "number_inpatient", "Prior Inpatient Visits"),
    (axes[1], "number_emergency", "Prior Emergency Visits"),
]:
    for val in ["no", ">30", "<30"]:
        subset = df[df[TARGET_COL] == val][col]
        sns.kdeplot(subset, ax=ax, label=val, color=palette[val], fill=True, alpha=0.35)
    ax.set_xlabel(title)
    ax.set_ylabel("Density")
    ax.set_title(title)
    ax.legend(title="Readmitted")

plt.tight_layout()
save(f"{PREFIX}07_kde_prior_visits.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t08 — Correlation heatmap (numeric columns only)
# ════════════════════════════════════════════════════════════════════════════════
numeric_cols = df.select_dtypes(include="number").columns.tolist()
# Exclude one-hot race columns and age midpoint (redundant with age_group)
exclude = race_cols + ["age"]
numeric_cols = [c for c in numeric_cols if c not in exclude]

corr = df[numeric_cols].corr()
mask = np.triu(np.ones_like(corr, dtype=bool))

fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(corr, mask=mask, annot=True, fmt=".2f",
            cmap="coolwarm", center=0, linewidths=0.5, ax=ax)
ax.set_title("Correlation Matrix — Numeric Features", fontsize=13, fontweight="bold")
plt.tight_layout()
save(f"{PREFIX}08_correlation_heatmap.png")


# ════════════════════════════════════════════════════════════════════════════════
# Chart t09 — Side-by-side box plots for all numeric features
# ════════════════════════════════════════════════════════════════════════════════
plot_cols = ["time_in_hospital", "num_lab_procedures", "num_medications",
             "number_emergency", "number_inpatient", "number_diagnoses"]

fig, axes = plt.subplots(2, 3, figsize=(16, 10))
fig.suptitle("Numeric Feature Distributions by Readmission Class", fontsize=14, fontweight="bold")

for ax, col in zip(axes.flat, plot_cols):
    sns.boxplot(data=df, x=TARGET_COL, y=col, order=["no", ">30", "<30"],
                hue=TARGET_COL, palette=palette, legend=False, ax=ax)
    ax.set_title(col.replace("_", " ").title())
    ax.set_xlabel("Readmitted")
    ax.set_ylabel("")

plt.tight_layout()
save(f"{PREFIX}09_all_numeric_boxplots.png")


# ════════════════════════════════════════════════════════════════════════════════
# Done
# ════════════════════════════════════════════════════════════════════════════════
print(f"\nDone — {len(saved)} charts saved to '{CHARTS_DIR}/'")
for name in saved:
    print(f"  {name}")
