"""Publication figures from an analysis table (matplotlib, 300 dpi PNG).

Plots only what is in the table. Every figure returns the n behind each
group so captions can state it. Colours are the Okabe–Ito colour-blind-safe
palette.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from aquaculture_manuscript_mcp.tools.farm_data import load_table  # noqa: E402

PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
KINDS = ("line", "scatter", "mean_bar", "box")


def make_figure(
    table_path: str,
    kind: str,
    x: str,
    y: str,
    output_path: str,
    group: str | None = None,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    resample: str | None = None,
    sheet: str | None = None,
) -> dict:
    """Make a figure.

    kind:
      "line"     — y over x (a date or time column), one line per group; use
                   resample="W" or "M" to plot weekly/monthly means of daily data.
      "scatter"  — y against x, coloured by group.
      "mean_bar" — mean ± SD of y for each x category (n shown on each bar).
      "box"      — distribution of y for each x category.

    For mean_bar and box, each row counts as one observation: aggregate the
    table to the experimental unit (one row per cage) first, or the error
    bars and n describe pseudo-replicates.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    df = load_table(table_path, sheet)
    for c in [x, y] + ([group] if group else []):
        if c not in df.columns:
            raise ValueError(f"column '{c}' not in the table. Columns: {list(df.columns)}")
    df = df.dropna(subset=[x, y])
    df[y] = pd.to_numeric(df[y], errors="coerce")
    df = df.dropna(subset=[y])
    if df.empty:
        raise ValueError("no rows with numeric values to plot")

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(7, 4.2))
    groups = list(df.groupby(group)) if group else [("all", df)]
    n_by_group: dict = {}

    if kind == "line":
        df[x] = pd.to_datetime(df[x], errors="coerce")
        df = df.dropna(subset=[x])
        groups = list(df.groupby(group)) if group else [("all", df)]
        for i, (name, g) in enumerate(groups):
            s = g.set_index(x)[y].sort_index()
            if resample:
                s = s.groupby(pd.Grouper(freq=resample)).mean().dropna()
            else:
                s = s.groupby(level=0).mean()
            ax.plot(s.index, s.values, color=PALETTE[i % len(PALETTE)], lw=1.4, label=str(name))
            n_by_group[str(name)] = int(len(g))
        fig.autofmt_xdate()
    elif kind == "scatter":
        df[x] = pd.to_numeric(df[x], errors="coerce")
        df = df.dropna(subset=[x])
        groups = list(df.groupby(group)) if group else [("all", df)]
        for i, (name, g) in enumerate(groups):
            ax.scatter(g[x], g[y], s=14, alpha=0.7, color=PALETTE[i % len(PALETTE)], label=str(name), edgecolors="none")
            n_by_group[str(name)] = int(len(g))
    else:
        cats = list(dict.fromkeys(df[x].sort_values()))
        if kind == "mean_bar":
            stats = df.groupby(x)[y].agg(["mean", "std", "count"]).reindex(cats)
            bars = ax.bar(range(len(cats)), stats["mean"], yerr=stats["std"], capsize=4,
                          color=[PALETTE[i % len(PALETTE)] for i in range(len(cats))], edgecolor="black", lw=0.6)
            for b, n in zip(bars, stats["count"]):
                ax.annotate(f"n={int(n)}", (b.get_x() + b.get_width() / 2, 0), xytext=(0, 3),
                            textcoords="offset points", ha="center", va="bottom", fontsize=8, color="white")
            n_by_group = {str(k): int(v) for k, v in stats["count"].items()}
        else:
            data = [df.loc[df[x] == c, y].values for c in cats]
            ax.boxplot(data, widths=0.6, patch_artist=True, boxprops={"facecolor": "#D9EAD3"}, medianprops={"color": "black"})
            n_by_group = {str(c): int(len(v)) for c, v in zip(cats, data)}
        ax.set_xticks(range(1 if kind == "box" else 0, len(cats) + (1 if kind == "box" else 0)))
        ax.set_xticklabels([str(c) for c in cats])

    ax.set_xlabel(x if xlabel is None else xlabel)  # "" means no label
    ax.set_ylabel(y if ylabel is None else ylabel)
    if title:
        ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    if group and kind in ("line", "scatter"):
        ax.legend(frameon=False, title=group)
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return {
        "file_path": output_path,
        "kind": kind,
        "x": x,
        "y": y,
        "group": group,
        "n_by_group": n_by_group,
        "error_bars": "mean ± SD" if kind == "mean_bar" else None,
        "resample": resample,
    }
