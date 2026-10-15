---
name: visualize-dataset
description: >
  Use this skill when the user provides a CSV file and wants to explore and
  visualize its contents. It covers inspecting the data, identifying the target
  column and feature types, writing a Python visualization script tailored to
  those features, running it, and saving every chart as a numbered PNG in a
  charts/ folder.
---

# Skill: Visualize Dataset

Given a CSV file, produce a full set of exploratory charts saved as PNG files.

## Steps

### 1. Unzip if needed

If the CSV is inside a zip archive, unzip it first:

```bash
unzip <archive>.zip
```

Confirm the extracted paths before continuing.

---

### 2. Inspect the data

Read the first few rows and record every column name and its apparent type
(numeric, low-cardinality categorical, binary flag, free text, etc.).

```bash
head -5 <path/to/file.csv>
wc -l <path/to/file.csv>
head -1 <path/to/file.csv> | tr ',' '\n' | nl
```

Key things to note:
- **Row count** — affects chart choice (KDE vs histogram, etc.)
- **Target column** — the column you want to explain or predict; it drives the
  colour/hue in most charts.
- **Categorical columns** — used for grouped bar charts.
- **Numeric columns** — used for distributions, box plots, and the correlation
  heatmap.
- **Encoded columns** — binary flags (0/1) or decade-encoded integers (e.g. age
  stored as 5, 15, 25 …) that need a label mapping before plotting.

---

### 3. Plan the charts

Based on the column inventory, decide which charts to include. A good default
set for a classification dataset is:

| # | Chart type | Purpose |
|---|-----------|---------|
| 1 | Pie + bar (side-by-side) | Target column distribution |
| 2–N | Grouped % bar | Target rate broken down by each categorical column |
| N+1 | Histogram (dodge) | Numeric column distributions split by target |
| N+2 | KDE density overlay | Smooth view of a high-cardinality numeric column |
| N+3 | Box plot | Spread of a numeric column per target class |
| N+4 | Violin plot | Distribution shape of a numeric column per target class |
| N+5 | Correlation heatmap | Pairwise correlations of all numeric columns |
| N+6 | Side-by-side box plots | Multiple related numeric columns in one figure |

Adjust the list freely — skip chart types that don't suit the data, add others
that do.

---

### 4. Write the visualization script

Create `visualize.py` (or a similarly named file) in the working directory.

**Script structure:**

```python
"""
<Dataset name> Visualization
Generates charts and saves them as PNG files in the charts/ folder.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import numpy as np

# ── Configuration ────────────────────────────────────────────────────────────
DATA_PATH  = "<path/to/file.csv>"   # ← update for each dataset
CHARTS_DIR = "charts"
TARGET_COL = "<target_column>"      # ← column that drives hue/colour

os.makedirs(CHARTS_DIR, exist_ok=True)
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({"figure.dpi": 150, "savefig.bbox": "tight"})

df = pd.read_csv(DATA_PATH)
print(f"Loaded {len(df):,} rows × {df.shape[1]} columns")

saved = []

def save(name: str):
    path = os.path.join(CHARTS_DIR, name)
    plt.savefig(path)
    plt.close()
    saved.append(name)
    print(f"  ✔  {name}")

# ... chart sections ...

print(f"\nDone — {len(saved)} charts saved to '{CHARTS_DIR}/'")
for name in saved:
    print(f"  {name}")
```

**Conventions to follow in every chart section:**

- Number output files sequentially: `01_`, `02_`, … so they sort cleanly.
- Use a consistent colour palette keyed on the target column's unique values.
- For categorical breakdown charts, compute percentages (not raw counts) so
  groups of different sizes are comparable:
  ```python
  grp = df.groupby([cat_col, TARGET_COL]).size().reset_index(name="count")
  grp["pct"] = grp["count"] / grp.groupby(cat_col)["count"].transform("sum") * 100
  ```
- Format y-axis tick labels with commas for large counts:
  ```python
  ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
  ```
- Apply `rotation=45, ha="right"` to x-tick labels whenever category names are
  longer than ~8 characters.
- Always call `plt.close()` after saving to free memory (the `save()` helper
  above handles this).

**Correlation heatmap pattern:**

```python
numeric_cols = df.select_dtypes(include="number").columns.tolist()
corr = df[numeric_cols].corr()
mask = np.triu(np.ones_like(corr, dtype=bool))   # hide upper triangle
fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(corr, mask=mask, annot=True, fmt=".2f",
            cmap="coolwarm", center=0, linewidths=0.5, ax=ax)
ax.set_title("Correlation Matrix – Numeric Features", fontsize=13, fontweight="bold")
save("NN_correlation_heatmap.png")
```

---

### 5. Install dependencies if missing

```bash
pip3 install pandas matplotlib seaborn numpy --quiet
```

---

### 6. Run the script and verify output

```bash
python3 visualize.py
ls charts/
```

All expected PNG files should be listed. If any chart section raises an error,
fix it and re-run. Common issues:

| Error | Fix |
|-------|-----|
| `KeyError` on pivot | A target value is missing from one group — use `.reindex()` or fill NaN with 0 |
| `FutureWarning` from seaborn boxplot/violin | Pass `hue=` and `legend=False` instead of `palette=` alone |
| `ModuleNotFoundError` | Run the pip install step above |
| Blank / empty chart | The column filter returned zero rows — check column name spelling |

---

### 7. Report results

After a successful run, list each chart file and one sentence describing what
it shows. Example:

```
charts/
  01_target_distribution.png   — Overall class balance (pie + bar)
  02_target_by_age.png         — Readmission rate across age groups
  ...
```

---

## Adaptation notes

- **No clear target column** (unsupervised / regression): skip grouped charts;
  focus on distributions, a pairplot (`sns.pairplot`), and the correlation
  heatmap.
- **Many numeric columns** (>15): replace individual box plots with a single
  `sns.pairplot` or a faceted grid to keep the chart count manageable.
- **Time-series data**: add a line chart of the key metric over time as the
  first chart.
- **Very large files** (>1 M rows): sample before plotting:
  ```python
  df = pd.read_csv(DATA_PATH).sample(100_000, random_state=42)
  ```
