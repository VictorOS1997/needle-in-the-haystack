# Needle in the Haystack: Q4 2024 sales data check

Data quality review of daily unit sales (50 SKUs x 50 states, Oct 1 to Dec 31, 2024), with a fix for the issue found and a memo for Customer Success.

## Data

The dataset is not included in the repo. Put the file you received at `data/sales.xlsx`, renamed exactly like that:

```
data/
  sales.xlsx    # columns: date, state, sku, units_sold
```

## Run

Requires Python 3.11+.

```
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python analysis.py
```

The script prints the checks and impact figures, saves the charts and writes the corrected data.

## Layout

```
data/sales.xlsx        input data (not in the repo, see Data)
analysis.py            checks, detection, fix and impact
charts/                charts used in the memo (generated)
output/sales_fixed.csv corrected data (generated)
memo.pdf               1-page memo plus appendix
```

## Finding

SKU-002, SKU-004 and SKU-012 were frozen at about half their normal daily level in 25 states (AK through MS) from Nov 8 to Nov 24, 2024: 1,275 rows and 55,488 missing units. Everything else checks out. The fix fills those rows with each series' Oct 1 to Nov 7 daily average. See memo.pdf for impact and next steps.
