from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DATA = Path("data/sales.xlsx")
CHARTS = Path("charts")
OUTPUT = Path("output")
KEYS = ["state", "sku"]


def load():
    if not DATA.exists():
        raise SystemExit(f"Dataset not found: put it at {DATA} (see README)")
    df = pd.read_excel(DATA)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(KEYS + ["date"]).reset_index(drop=True)


def integrity_report(df):
    days = pd.date_range(df["date"].min(), df["date"].max())
    expected = df["state"].nunique() * df["sku"].nunique() * len(days)
    return {
        "rows": len(df),
        "expected rows": expected,
        "nulls": int(df.isna().sum().sum()),
        "duplicate keys": int(df.duplicated(KEYS + ["date"]).sum()),
        "negative units": int((df["units_sold"] < 0).sum()),
        "missing days": len(days.difference(df["date"].unique())),
    }


def find_flat_runs(df, min_days=14):
    # Low-volume SKUs repeat the same small number for up to ~11 days by chance;
    # two weeks of identical values is not plausible sales.
    run_id = df.groupby(KEYS)["units_sold"].diff().ne(0).cumsum()
    runs = df.groupby(run_id).agg(
        state=("state", "first"),
        sku=("sku", "first"),
        start=("date", "min"),
        end=("date", "max"),
        days=("date", "size"),
        units=("units_sold", "first"),
    )
    return runs[runs["days"] >= min_days]


def flag_bad_rows(df, runs):
    start, end = runs["start"].mode()[0], runs["end"].mode()[0]
    series = runs.set_index(KEYS).index
    in_series = df.set_index(KEYS).index.isin(series)
    return in_series & df["date"].between(start, end), start, end


def fix(df, bad, window_start):
    # Each frozen value is exactly half of that series' Oct 1 - Nov 7 average,
    # so that same average is the best estimate of the true daily level.
    baseline = df[df["date"] < window_start].groupby(KEYS)["units_sold"].mean()
    fixed = df.copy()
    keys = pd.MultiIndex.from_frame(df.loc[bad, KEYS])
    fixed.loc[bad, "units_sold"] = baseline.reindex(keys).round().astype(int).to_numpy()
    return fixed


def impact_by_sku(df, fixed, skus):
    reported = df[df["sku"].isin(skus)].groupby("sku")["units_sold"].sum()
    corrected = fixed[fixed["sku"].isin(skus)].groupby("sku")["units_sold"].sum()
    out = pd.DataFrame({"reported": reported, "corrected": corrected})
    out["missing"] = out["corrected"] - out["reported"]
    out["understated %"] = (out["missing"] / out["corrected"] * 100).round(1)
    return out


def sku_ranks(df):
    return df.groupby("sku")["units_sold"].sum().rank(ascending=False).astype(int)


def plot_daily(df, fixed, bad_states, skus, start, end):
    scope = df["sku"].isin(skus)
    group = df["state"].isin(bad_states).map({True: "Affected states", False: "Other states"})
    reported = df[scope].groupby([df["date"], group])["units_sold"].sum().unstack()
    corrected = fixed[scope & df["state"].isin(bad_states)].groupby("date")["units_sold"].sum()

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(reported.index, reported["Other states"], color="grey", label="Other 25 states (reported)")
    ax.plot(reported.index, reported["Affected states"], color="firebrick", label="Affected 25 states (reported)")
    ax.plot(corrected.loc[start:end].index, corrected.loc[start:end], color="firebrick",
            linestyle="--", label="Affected 25 states (corrected)")
    ax.axvspan(start, end, color="firebrick", alpha=0.08)
    ax.set_title(f"Daily units, {', '.join(skus)}: frozen at half volume {start:%b %d} - {end:%b %d}")
    ax.set_ylabel("Units sold")
    ax.set_ylim(0)
    ax.legend(loc="lower left", frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "daily_units_affected_vs_other.png", dpi=150)
    plt.close(fig)


def plot_example(df, fixed, state, sku, start, end):
    mask = (df["state"] == state) & (df["sku"] == sku)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(df.loc[mask, "date"], df.loc[mask, "units_sold"], color="firebrick", label="Reported")
    window = mask & df["date"].between(start, end)
    ax.plot(fixed.loc[window, "date"], fixed.loc[window, "units_sold"], color="black",
            linestyle="--", label="Corrected")
    ax.axvspan(start, end, color="firebrick", alpha=0.08)
    ax.set_title(f"{state} / {sku}: daily units, reported vs corrected")
    ax.set_ylabel("Units sold")
    ax.set_ylim(0)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / f"example_{state}_{sku}.png", dpi=150)
    plt.close(fig)


def main():
    CHARTS.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    df = load()
    print("Integrity checks:", integrity_report(df))

    runs = find_flat_runs(df)
    bad, start, end = flag_bad_rows(df, runs)
    bad_states = sorted(df.loc[bad, "state"].unique())
    bad_skus = sorted(df.loc[bad, "sku"].unique())
    print(f"\nFrozen values: {bad.sum()} rows ({bad.mean():.2%} of data), "
          f"{start:%Y-%m-%d} to {end:%Y-%m-%d} ({(end - start).days + 1} days)")
    print(f"SKUs: {', '.join(bad_skus)}")
    print(f"States ({len(bad_states)}): {', '.join(bad_states)}")

    fixed = fix(df, bad, start)
    ratio = df.loc[bad, "units_sold"].sum() / fixed.loc[bad, "units_sold"].sum()
    print(f"Reported values in the window are {ratio:.0%} of the corrected level")

    missing = fixed["units_sold"].sum() - df["units_sold"].sum()
    print(f"\nUnits missing: {missing:,} "
          f"({missing / fixed['units_sold'].sum():.1%} of all Q4 units)")
    print("\nQ4 national totals for affected SKUs:")
    print(impact_by_sku(df, fixed, bad_skus).to_string())

    in_affected = df["sku"].isin(bad_skus) & df["state"].isin(bad_states)
    window = df["date"].between(start, end)
    for label, rows in [("affected states, Q4", in_affected),
                        ("affected states, inside window", in_affected & window)]:
        r, c = df.loc[rows, "units_sold"].sum(), fixed.loc[rows, "units_sold"].sum()
        print(f"Affected SKUs, {label}: reported {r:,} vs corrected {c:,} ({(r - c) / c:+.1%})")

    for name, data in [("reported", df), ("corrected", fixed)]:
        scope = data[data["sku"].isin(bad_skus)]
        monthly = scope.groupby(scope["date"].dt.month)["units_sold"].sum()
        print(f"Affected SKUs Nov vs Oct, {name}: {monthly[11] / monthly[10] - 1:+.1%}")

    ranks = pd.DataFrame({"reported": sku_ranks(df), "corrected": sku_ranks(fixed)})
    moved = ranks[ranks["reported"] != ranks["corrected"]]
    print("\nNational SKU rank changes after fix:")
    print(moved.sort_values("corrected").to_string())

    plot_daily(df, fixed, bad_states, bad_skus, start, end)
    plot_example(df, fixed, "CA", "SKU-002", start, end)

    fixed.to_csv(OUTPUT / "sales_fixed.csv", index=False, date_format="%Y-%m-%d")
    print(f"\nCorrected data written to {OUTPUT / 'sales_fixed.csv'}")


if __name__ == "__main__":
    main()
