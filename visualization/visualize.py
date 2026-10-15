"""
Diabetic Readmission Data Visualization
Generates charts and saves them as PNG files in the charts/ folder.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import numpy as np

# ── Setup ────────────────────────────────────────────────────────────────────
DATA_PATH = "diabetic/data/diabetic_readmission.csv"
CHARTS_DIR = "charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({"figure.dpi": 150, "savefig.bbox": "tight"})

df = pd.read_csv(DATA_PATH)

# Normalise the age column: stored as decade midpoints (5, 15, 25 …)
# Map to readable labels for categorical plots
age_labels = {
    5: "[0-10)", 15: "[10-20)", 25: "[20-30)", 35: "[30-40)",
    45: "[40-50)", 55: "[50-60)", 65: "[60-70)", 75: "[70-80)",
    85: "[80-90)", 95: "[90-100)",
}
df["age_group"] = df["age"].map(age_labels).fillna(df["age"].astype(str))

READMIT_ORDER = ["no", ">30", "<30"]
READMIT_PALETTE = {"no": "#4C72B0", ">30": "#DD8452", "<30": "#C44E52"}

print(f"Loaded {len(df):,} rows × {df.shape[1]} columns")
print(f"Saving charts to: {CHARTS_DIR}/\n")

saved = []

def save(name: str):
    path = os.path.join(CHARTS_DIR, name)
    plt.savefig(path)
    plt.close()
    saved.append(name)
    print(f"  ✔  {name}")


# ── 1. Readmission Distribution (pie + bar side-by-side) ────────────────────
counts = df["readmitted"].value_counts().reindex(READMIT_ORDER)

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Readmission Distribution", fontsize=14, fontweight="bold")

axes[0].pie(
    counts,
    labels=counts.index,
    autopct="%1.1f%%",
    colors=[READMIT_PALETTE[k] for k in counts.index],
    startangle=140,
    wedgeprops={"edgecolor": "white", "linewidth": 1.5},
)
axes[0].set_title("Proportion")

axes[1].bar(counts.index, counts.values,
            color=[READMIT_PALETTE[k] for k in counts.index], edgecolor="white")
axes[1].set_xlabel("Readmission")
axes[1].set_ylabel("Patient Count")
axes[1].set_title("Counts")
axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
for bar, val in zip(axes[1].patches, counts.values):
    axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 200,
                 f"{val:,}", ha="center", va="bottom", fontsize=9)

save("01_readmission_distribution.png")


# ── 2. Readmission by Age Group ──────────────────────────────────────────────
age_order = [age_labels[k] for k in sorted(age_labels)]
age_read = (
    df.groupby(["age_group", "readmitted"])
    .size()
    .reset_index(name="count")
)
age_totals = age_read.groupby("age_group")["count"].transform("sum")
age_read["pct"] = age_read["count"] / age_totals * 100

fig, ax = plt.subplots(figsize=(12, 5))
pivot = age_read.pivot(index="age_group", columns="readmitted", values="pct").reindex(age_order)
pivot[READMIT_ORDER].plot(
    kind="bar", ax=ax, color=[READMIT_PALETTE[k] for k in READMIT_ORDER],
    edgecolor="white", width=0.75,
)
ax.set_title("Readmission Rate by Age Group", fontsize=13, fontweight="bold")
ax.set_xlabel("Age Group")
ax.set_ylabel("Percentage (%)")
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")
ax.legend(title="Readmitted")
save("02_readmission_by_age.png")


# ── 3. Readmission by Race ───────────────────────────────────────────────────
race_read = (
    df.groupby(["race", "readmitted"])
    .size()
    .reset_index(name="count")
)
race_totals = race_read.groupby("race")["count"].transform("sum")
race_read["pct"] = race_read["count"] / race_totals * 100

fig, ax = plt.subplots(figsize=(11, 5))
pivot = race_read.pivot(index="race", columns="readmitted", values="pct")
pivot[READMIT_ORDER].plot(
    kind="bar", ax=ax, color=[READMIT_PALETTE[k] for k in READMIT_ORDER],
    edgecolor="white", width=0.7,
)
ax.set_title("Readmission Rate by Race", fontsize=13, fontweight="bold")
ax.set_xlabel("Race")
ax.set_ylabel("Percentage (%)")
ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right")
ax.legend(title="Readmitted")
save("03_readmission_by_race.png")


# ── 4. Readmission by Gender ─────────────────────────────────────────────────
gender_read = (
    df.groupby(["gender", "readmitted"])
    .size()
    .reset_index(name="count")
)
gender_totals = gender_read.groupby("gender")["count"].transform("sum")
gender_read["pct"] = gender_read["count"] / gender_totals * 100

fig, ax = plt.subplots(figsize=(7, 5))
pivot = gender_read.pivot(index="gender", columns="readmitted", values="pct")
pivot[READMIT_ORDER].plot(
    kind="bar", ax=ax, color=[READMIT_PALETTE[k] for k in READMIT_ORDER],
    edgecolor="white", width=0.5,
)
ax.set_title("Readmission Rate by Gender", fontsize=13, fontweight="bold")
ax.set_xlabel("Gender")
ax.set_ylabel("Percentage (%)")
ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
ax.legend(title="Readmitted")
save("04_readmission_by_gender.png")


# ── 5. Time in Hospital Distribution ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
sns.histplot(
    data=df, x="time_in_hospital", hue="readmitted",
    hue_order=READMIT_ORDER, palette=READMIT_PALETTE,
    bins=14, multiple="dodge", shrink=0.85, ax=ax,
)
ax.set_title("Time in Hospital by Readmission Status", fontsize=13, fontweight="bold")
ax.set_xlabel("Days in Hospital")
ax.set_ylabel("Patient Count")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
save("05_time_in_hospital.png")


# ── 6. Number of Lab Procedures Distribution ─────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
for label in READMIT_ORDER:
    subset = df[df["readmitted"] == label]["num_lab_procedures"]
    sns.kdeplot(subset, ax=ax, label=label, color=READMIT_PALETTE[label], fill=True, alpha=0.25)
ax.set_title("Lab Procedures Distribution by Readmission Status", fontsize=13, fontweight="bold")
ax.set_xlabel("Number of Lab Procedures")
ax.set_ylabel("Density")
ax.legend(title="Readmitted")
save("06_lab_procedures_distribution.png")


# ── 7. Number of Medications Distribution ────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
sns.boxplot(
    data=df, x="readmitted", y="num_medications",
    order=READMIT_ORDER, palette=READMIT_PALETTE,
    width=0.5, flierprops={"marker": ".", "alpha": 0.3}, ax=ax,
)
ax.set_title("Number of Medications by Readmission Status", fontsize=13, fontweight="bold")
ax.set_xlabel("Readmitted")
ax.set_ylabel("Number of Medications")
save("07_medications_boxplot.png")


# ── 8. Number of Diagnoses Distribution ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
sns.violinplot(
    data=df, x="readmitted", y="number_diagnoses",
    order=READMIT_ORDER, palette=READMIT_PALETTE,
    inner="quartile", ax=ax,
)
ax.set_title("Number of Diagnoses by Readmission Status", fontsize=13, fontweight="bold")
ax.set_xlabel("Readmitted")
ax.set_ylabel("Number of Diagnoses")
save("08_diagnoses_violin.png")


# ── 9. A1C Result vs Readmission ─────────────────────────────────────────────
a1c_read = (
    df.groupby(["a1c_result", "readmitted"])
    .size()
    .reset_index(name="count")
)
a1c_totals = a1c_read.groupby("a1c_result")["count"].transform("sum")
a1c_read["pct"] = a1c_read["count"] / a1c_totals * 100

fig, ax = plt.subplots(figsize=(9, 5))
pivot = a1c_read.pivot(index="a1c_result", columns="readmitted", values="pct")
pivot[READMIT_ORDER].plot(
    kind="bar", ax=ax, color=[READMIT_PALETTE[k] for k in READMIT_ORDER],
    edgecolor="white", width=0.65,
)
ax.set_title("Readmission Rate by A1C Result", fontsize=13, fontweight="bold")
ax.set_xlabel("A1C Result")
ax.set_ylabel("Percentage (%)")
ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
ax.legend(title="Readmitted")
save("09_a1c_result_vs_readmission.png")


# ── 10. Max Glucose Serum vs Readmission ─────────────────────────────────────
glu_read = (
    df.groupby(["max_glu_serum", "readmitted"])
    .size()
    .reset_index(name="count")
)
glu_totals = glu_read.groupby("max_glu_serum")["count"].transform("sum")
glu_read["pct"] = glu_read["count"] / glu_totals * 100

fig, ax = plt.subplots(figsize=(9, 5))
pivot = glu_read.pivot(index="max_glu_serum", columns="readmitted", values="pct")
pivot[READMIT_ORDER].plot(
    kind="bar", ax=ax, color=[READMIT_PALETTE[k] for k in READMIT_ORDER],
    edgecolor="white", width=0.65,
)
ax.set_title("Readmission Rate by Max Glucose Serum", fontsize=13, fontweight="bold")
ax.set_xlabel("Max Glucose Serum")
ax.set_ylabel("Percentage (%)")
ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
ax.legend(title="Readmitted")
save("10_glucose_serum_vs_readmission.png")


# ── 11. Diabetes Medication & Change ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Medication Factors vs Readmission", fontsize=13, fontweight="bold")

for ax, col, title in zip(
    axes,
    ["diabetes_med", "change"],
    ["Diabetes Medication Prescribed", "Medication Change"],
):
    grp = (
        df.groupby([col, "readmitted"])
        .size()
        .reset_index(name="count")
    )
    totals = grp.groupby(col)["count"].transform("sum")
    grp["pct"] = grp["count"] / totals * 100
    pivot = grp.pivot(index=col, columns="readmitted", values="pct")
    pivot[READMIT_ORDER].plot(
        kind="bar", ax=ax, color=[READMIT_PALETTE[k] for k in READMIT_ORDER],
        edgecolor="white", width=0.5,
    )
    ax.set_title(title)
    ax.set_xlabel(col)
    ax.set_ylabel("Percentage (%)")
    ax.set_xticklabels(["No (0)", "Yes (1)"], rotation=0)
    ax.legend(title="Readmitted")

save("11_medication_factors.png")


# ── 12. Correlation Heatmap (numeric features) ───────────────────────────────
numeric_cols = [
    "time_in_hospital", "num_lab_procedures", "num_procedures",
    "num_medications", "number_outpatient", "number_emergency",
    "number_inpatient", "number_diagnoses",
]
corr = df[numeric_cols].corr()

fig, ax = plt.subplots(figsize=(10, 8))
mask = np.triu(np.ones_like(corr, dtype=bool))
sns.heatmap(
    corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
    center=0, linewidths=0.5, ax=ax,
)
ax.set_title("Correlation Matrix – Numeric Features", fontsize=13, fontweight="bold")
save("12_correlation_heatmap.png")


# ── 13. Inpatient / Emergency / Outpatient Visits ────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle("Prior Visit Counts by Readmission Status", fontsize=13, fontweight="bold")

for ax, col in zip(axes, ["number_inpatient", "number_emergency", "number_outpatient"]):
    sns.boxplot(
        data=df, x="readmitted", y=col,
        order=READMIT_ORDER, palette=READMIT_PALETTE,
        width=0.5, flierprops={"marker": ".", "alpha": 0.2}, ax=ax,
    )
    ax.set_title(col.replace("number_", "").capitalize())
    ax.set_xlabel("Readmitted")
    ax.set_ylabel("Visit Count")

save("13_prior_visits_boxplots.png")


# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\nDone — {len(saved)} charts saved to '{CHARTS_DIR}/'")
for name in saved:
    print(f"  {name}")
