---
name: dataset-bias-audit
description: Check a health dataset for bias between demographic groups and write a short report with charts. Use when asked about bias, fairness, or data quality in a dataset.
---

# Dataset bias audit

Check the CSV file the user names for bias.
If no file is named, use the largest CSV file in this folder.

1. Representation: count the records in each demographic group, such as age, gender, and race. Flag groups that are very small or have many missing values.
2. Outcomes: compare the outcome rate, such as readmission, for each group with the overall rate. Flag groups that differ by more than 5 percentage points.
3. Missing data: check whether some measurements are missing more often for some groups than for others.
4. Charts: save one chart for each check as a PNG file in the charts/ folder.
5. Report: write BIAS_REPORT.md with a plain-language summary of what you found, the charts, and the limitations of this dataset.

Never print or copy raw patient rows.
