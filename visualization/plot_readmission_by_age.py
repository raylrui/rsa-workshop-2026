#!/usr/bin/env python3
"""Plot readmission rate by age group."""

import pandas as pd
import matplotlib.pyplot as plt

# Load the dataset
df = pd.read_csv('diabetic/data/diabetic_readmission.csv')

# Calculate readmission rate by age group
# readmitted can be 'no', '<30', or '>30' - we consider both '<30' and '>30' as readmitted
df['is_readmitted'] = df['readmitted'].apply(lambda x: 1 if x != 'no' else 0)

# Group by age and calculate readmission rate
age_groups = df.groupby('age').agg(
    readmission_rate=('is_readmitted', 'mean'),
    total_patients=('is_readmitted', 'count')
).reset_index()

# Sort by age group (they appear to be age ranges)
age_groups['age'] = pd.Categorical(age_groups['age'], 
                                    categories=sorted(age_groups['age'].unique()),
                                    ordered=True)
age_groups = age_groups.sort_values('age')

# Create the plot
plt.figure(figsize=(12, 6))
bars = plt.bar(range(len(age_groups)), age_groups['readmission_rate'], 
               color='steelblue', edgecolor='black', alpha=0.7)

plt.xlabel('Age Group', fontsize=12, fontweight='bold')
plt.ylabel('Readmission Rate', fontsize=12, fontweight='bold')
plt.title('Hospital Readmission Rate by Age Group', fontsize=14, fontweight='bold')
plt.xticks(range(len(age_groups)), age_groups['age'], rotation=45, ha='right')
plt.ylim(0, max(age_groups['readmission_rate']) * 1.1)

# Add percentage labels on bars
for i, (rate, count) in enumerate(zip(age_groups['readmission_rate'], 
                                       age_groups['total_patients'])):
    plt.text(i, rate, f'{rate*100:.1f}%\n(n={count})', 
             ha='center', va='bottom', fontsize=9)

plt.grid(axis='y', alpha=0.3, linestyle='--')
plt.tight_layout()

# Save the chart
plt.savefig('charts/readmission_by_age_group.png', dpi=300, bbox_inches='tight')
print("Chart saved to charts/readmission_by_age_group.png")

# Print summary statistics
print("\nReadmission Rate by Age Group:")
print("="*50)
for _, row in age_groups.iterrows():
    print(f"{row['age']:>10}: {row['readmission_rate']*100:5.1f}% (n={row['total_patients']:,})")
