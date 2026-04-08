import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from packaging.version import Version

from calculate_fanin_and_fanout import load_deps, calculate_metrics


deps_dir = Path(__file__).parent / "deps"
ck_dir = Path(__file__).parent / "ck_metrics"
lcom_dir = Path(__file__).parent / "lcom_metrics"
sm_dir = Path(__file__).parent / "sm_metrics"
sm_results_dir = Path(__file__).parent / "sm_results"

_LATEST_SENTINEL = Version("99999.0.0")


def version_sort_key(v: str) -> Version:
    stripped = v.lstrip("v")
    if stripped == "latest":
        return _LATEST_SENTINEL
    return Version(stripped)


versions_in_order_of_release: list[str] = sorted(
    [p.stem for p in deps_dir.glob("*.json")],
    key=version_sort_key,
)

ck_versions_in_order: list[str] = sorted(
    [p.stem for p in ck_dir.glob("*.json") if (deps_dir / p.name).exists()],
    key=version_sort_key,
)


def compute_instability(version: str) -> float:
    path = deps_dir / f"{version}.json"
    deps = load_deps(path)
    metrics = calculate_metrics(deps)
    instabilities = [
        v["fan_out"] / (v["fan_in"] + v["fan_out"])
        for v in metrics
        if v["fan_in"] + v["fan_out"] > 0
    ]
    return sum(instabilities) / len(instabilities) if instabilities else 0.0


def compute_avg_cbo(version: str) -> float:
    path = deps_dir / f"{version}.json"
    deps = load_deps(path)
    metrics = calculate_metrics(deps)
    fan_outs = [v["fan_out"] for v in metrics]
    return sum(fan_outs) / len(fan_outs) if fan_outs else 0.0


def compute_avg_rfc(version: str) -> float:
    path = deps_dir / f"{version}.json"
    deps = load_deps(path)
    metrics = calculate_metrics(deps)
    rfcs = [v["fan_in"] + v["fan_out"] for v in metrics]
    return sum(rfcs) / len(rfcs) if rfcs else 0.0


def compute_mq(version: str) -> float:
    """Modularity Quality = 1 - Coupling Factor.

    Coupling Factor (CF) = total directed inter-module edges / n*(n-1),
    i.e. the fraction of all possible module-to-module dependencies that
    actually exist (excluding self-loops and test modules).
    MQ in [0, 1]: higher means less coupling, better modularity.
    """
    path = deps_dir / f"{version}.json"
    deps = load_deps(path)
    metrics = calculate_metrics(deps)
    n = len(metrics)
    if n < 2:
        return 1.0
    total_edges = sum(v["fan_out"] for v in metrics)
    max_edges = n * (n - 1)
    cf = total_edges / max_edges
    return 1.0 - cf


def load_ck_summary(version: str) -> dict:
    path = ck_dir / f"{version}.json"
    data = json.loads(path.read_text())
    return data["summary"]


def load_sm_cr(version: str) -> float | None:
    """Read Clone Ratio (CR) from the raw SourceMeter summary JSON."""
    # Check processed metrics first (for future runs of the generator)
    metrics_path = sm_dir / f"{version}.json"
    if metrics_path.exists():
        data = json.loads(metrics_path.read_text())
        cr = data.get("clone_metrics", {}).get("clone_ratio")
        if cr is not None:
            return float(cr)

    # Fall back to raw sm_results output
    raw_dir = sm_results_dir / version.lstrip("v") / "icalendar" / "python"
    if not raw_dir.exists():
        return None
    dated_dirs = sorted(raw_dir.glob("*"))
    if not dated_dirs:
        return None
    summary_path = dated_dirs[-1] / "icalendar-summary.json"
    if not summary_path.exists():
        return None
    data = json.loads(summary_path.read_text())
    for attr in data["nodes"][0]["attributes"]:
        if attr["name"] == "CR":
            return float(attr["value"]) * 100  # express as percentage
    return None


def load_sm_tlloc(version: str) -> float | None:
    """Read Total Logical Lines of Code (TLLOC) from the raw SourceMeter summary JSON."""
    raw_dir = sm_results_dir / version.lstrip("v") / "icalendar" / "python"
    if not raw_dir.exists():
        return None
    dated_dirs = sorted(raw_dir.glob("*"))
    if not dated_dirs:
        return None
    summary_path = dated_dirs[-1] / "icalendar-summary.json"
    if not summary_path.exists():
        return None
    data = json.loads(summary_path.read_text())
    for attr in data["nodes"][0]["attributes"]:
        if attr["name"] == "TLLOC":
            return float(attr["value"])
    return None


def load_lcom_warnings_per_module(version: str) -> float:
    path = lcom_dir / f"{version}.json"
    data = json.loads(path.read_text())
    return data["summary"]["warnings_per_module"]


def plot_series(
    ax: plt.Axes,  # pyright: ignore[reportPrivateImportUsage]
    versions: list[str],
    values: list[float],
    title: str,
    ylabel: str,
    color: str,
) -> None:
    x = list(range(len(versions)))
    ax.plot(x, values, marker="o", color=color, linewidth=2, markersize=6)
    for i, (ver, val) in enumerate(zip(versions, values)):
        ax.annotate(
            ver,
            (i, val),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=7,
            rotation=45,
        )
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xticklabels(versions, rotation=45, ha="right", fontsize=7)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.2f}"))
    padding = (max(values) - min(values)) * 0.5 or 0.05
    ax.set_ylim(min(values) - padding, max(values) + padding)
    ax.grid(axis="y", linestyle="--", alpha=0.5)


def normalize(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    span = hi - lo
    return [((v - lo) / span) if span else 0.5 for v in values]


def save_overlay_graph(
    series: list[tuple[list[str], list[float], str, str]],
    title: str,
    filename: str,
    graphs_dir: Path,
    legend_loc: str = "upper left",
) -> None:
    """Plot multiple metrics on one normalised (0-1) axis.

    Each entry in *series* is (versions, values, label, color).
    Values are min-max normalised so metrics with different units are comparable.
    """
    if not series:
        return

    fig, ax = plt.subplots(figsize=(14, 6))

    all_x_labels: list[str] = []
    for versions, _, _, _ in series:
        for v in versions:
            if v not in all_x_labels:
                all_x_labels.append(v)
    all_x_labels = sorted(all_x_labels, key=version_sort_key)
    x_index = {v: i for i, v in enumerate(all_x_labels)}

    for versions, values, label, color in series:
        normed = normalize(values)
        xs = [x_index[v] for v in versions]
        ax.plot(xs, normed, marker="o", linewidth=2, markersize=5, label=label, color=color)

    ax.set_title(title)
    ax.set_ylabel("Normalised value (0 = min, 1 = max per metric)")
    ax.set_xticks(range(len(all_x_labels)))
    ax.set_xticklabels(all_x_labels, rotation=45, ha="right", fontsize=7)
    ax.set_ylim(-0.1, 1.1)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.2f}"))
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(loc=legend_loc, fontsize=8, framealpha=0.8)

    plt.tight_layout()
    output_path = graphs_dir / filename
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {output_path}")
    plt.close(fig)


def save_dual_axis_graph(
    versions: list[str],
    left_values: list[float],
    left_label: str,
    left_color: str,
    right_values: list[float],
    right_label: str,
    right_color: str,
    title: str,
    filename: str,
    graphs_dir: Path,
) -> None:
    if not versions:
        return
    fig, ax_left = plt.subplots(figsize=(12, 5))
    ax_right = ax_left.twinx()

    x = list(range(len(versions)))

    ax_left.plot(x, left_values, marker="o", color=left_color, linewidth=2, markersize=6, label=left_label)
    ax_right.plot(x, right_values, marker="s", color=right_color, linewidth=2, markersize=6, label=right_label, linestyle="--")

    ax_left.set_title(title)
    ax_left.set_ylabel(left_label, color=left_color)
    ax_left.tick_params(axis="y", labelcolor=left_color)
    ax_left.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.3f}"))

    ax_right.set_ylabel(right_label, color=right_color)
    ax_right.tick_params(axis="y", labelcolor=right_color)
    ax_right.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.3f}"))

    ax_left.set_xticks(x)
    ax_left.set_xticklabels(versions, rotation=45, ha="right", fontsize=7)
    ax_left.grid(axis="y", linestyle="--", alpha=0.4)

    lines_left, labels_left = ax_left.get_legend_handles_labels()
    lines_right, labels_right = ax_right.get_legend_handles_labels()
    ax_left.legend(lines_left + lines_right, labels_left + labels_right, loc="lower right", fontsize=8, framealpha=0.8)

    plt.tight_layout()
    output_path = graphs_dir / filename
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {output_path}")
    plt.close(fig)


def save_subplot_graph(
    series: list[tuple[list[str], list[float], str, str]],
    title: str,
    filename: str,
    graphs_dir: Path,
) -> None:
    """Plot multiple metrics as vertically stacked subplots sharing an x-axis.

    Each entry in *series* is (versions, values, label, color).
    Each subplot gets its own y-axis so raw values are preserved.
    """
    if not series:
        return

    n = len(series)
    fig, axes = plt.subplots(n, 1, figsize=(14, 3.5 * n), sharex=True)
    if n == 1:
        axes = [axes]

    all_versions: list[str] = []
    for versions, _, _, _ in series:
        for v in versions:
            if v not in all_versions:
                all_versions.append(v)
    all_versions = sorted(all_versions, key=version_sort_key)
    x_index = {v: i for i, v in enumerate(all_versions)}

    for ax, (versions, values, label, color) in zip(axes, series):
        xs = [x_index[v] for v in versions]
        ax.plot(xs, values, marker="o", color=color, linewidth=2, markersize=5)
        ax.set_ylabel(label, color=color, fontsize=9)
        ax.tick_params(axis="y", labelcolor=color)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.2f}"))
        padding = (max(values) - min(values)) * 0.3 or 1
        ax.set_ylim(min(values) - padding, max(values) + padding)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_xticks(range(len(all_versions)))
        ax.set_xticklabels([""] * len(all_versions))

    axes[-1].set_xticklabels(all_versions, rotation=45, ha="right", fontsize=7)
    axes[0].set_title(title)

    plt.tight_layout()
    output_path = graphs_dir / filename
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {output_path}")
    plt.close(fig)


def save_graph(versions: list[str], values: list[float], title: str, ylabel: str,
               color: str, filename: str, graphs_dir: Path) -> None:
    if not versions:
        return
    fig, ax = plt.subplots(figsize=(12, 5))
    plot_series(ax, versions, values, title, ylabel, color=color)
    plt.tight_layout()
    output_path = graphs_dir / filename
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {output_path}")
    plt.close(fig)


if __name__ == "__main__":
    graphs_dir = Path(__file__).parent / "graphs"
    graphs_dir.mkdir(exist_ok=True)

    all_instabilities = {v: compute_instability(v) for v in versions_in_order_of_release}

    all_v  = versions_in_order_of_release
    v4x = [v for v in all_v if v.startswith("v4")]
    v5x = [v for v in all_v if v.startswith("v5")]
    v6x = [v for v in all_v if v.startswith("v6")]
    v7x = [v for v in all_v if v.startswith("v7")]

    instability_graphs = [
        (all_v, "All Versions — Instability Rate",  "steelblue",    "instability_all.png"),
        (v4x,   "4.x Releases — Instability Rate",  "mediumpurple", "instability_4x.png"),
        (v5x,   "5.x Releases — Instability Rate",  "crimson",      "instability_5x.png"),
        (v6x,   "6.x Releases — Instability Rate",  "darkorange",   "instability_6x.png"),
        (v7x,   "7.x Releases — Instability Rate",  "seagreen",     "instability_7x.png"),
    ]

    for versions, title, color, filename in instability_graphs:
        save_graph(
            versions, [all_instabilities[v] for v in versions],
            title, "Instability Rate", color, filename, graphs_dir,
        )

    all_cbo = {v: compute_avg_cbo(v) for v in versions_in_order_of_release}
    save_graph(
        versions_in_order_of_release,
        [all_cbo[v] for v in versions_in_order_of_release],
        "All Versions — Avg CBO (fan-out per module)",
        "Avg CBO",
        "crimson",
        "cbo_all.png",
        graphs_dir,
    )

    all_rfc = {v: compute_avg_rfc(v) for v in versions_in_order_of_release}
    save_graph(
        versions_in_order_of_release,
        [all_rfc[v] for v in versions_in_order_of_release],
        "All Versions — Avg RFC (fan-in + fan-out per module)",
        "Avg RFC",
        "teal",
        "rfc_all.png",
        graphs_dir,
    )

    all_mq = {v: compute_mq(v) for v in versions_in_order_of_release}
    mq_graphs = [
        (all_v, "All Versions — Modularity Quality (MQ)",  "steelblue",    "mq_all.png"),
        (v4x,   "4.x Releases — Modularity Quality (MQ)",  "mediumpurple", "mq_4x.png"),
        (v5x,   "5.x Releases — Modularity Quality (MQ)",  "crimson",      "mq_5x.png"),
        (v6x,   "6.x Releases — Modularity Quality (MQ)",  "darkorange",   "mq_6x.png"),
        (v7x,   "7.x Releases — Modularity Quality (MQ)",  "seagreen",     "mq_7x.png"),
    ]
    for versions, title, color, filename in mq_graphs:
        save_graph(
            versions, [all_mq[v] for v in versions],
            title, "MQ (1 − Coupling Factor)", color, filename, graphs_dir,
        )

    save_dual_axis_graph(
        versions=all_v,
        left_values=[all_instabilities[v] for v in all_v],
        left_label="Instability Rate",
        left_color="steelblue",
        right_values=[all_mq[v] for v in all_v],
        right_label="MQ (1 − Coupling Factor)",
        right_color="seagreen",
        title="Instability Rate vs Modularity Quality — All Versions",
        filename="mq_vs_instability.png",
        graphs_dir=graphs_dir,
    )

    lcom_versions = sorted(
        [p.stem for p in lcom_dir.glob("*.json")],
        key=version_sort_key,
    )
    if lcom_versions:
        save_graph(
            lcom_versions,
            [load_lcom_warnings_per_module(v) for v in lcom_versions],
            "All Versions — LCOM (Pylint design warnings per module)",
            "Warnings / Module",
            "darkorange",
            "lcom_all.png",
            graphs_dir,
        )

    all_ck = {v: load_ck_summary(v) for v in ck_versions_in_order}

    ck_metrics = [
        ("avg_wmc",  "Avg WMC (Weighted Methods per Class)", "steelblue",    "ck_wmc.png"),
        ("avg_rfc",  "Avg RFC (Response for a Class)",       "mediumpurple", "ck_rfc.png"),
        ("avg_cbo",  "Avg CBO (Coupling Between Objects)",   "crimson",      "ck_cbo.png"),
        ("avg_lcom", "Avg LCOM (Lack of Cohesion)",          "darkorange",   "ck_lcom.png"),
    ]

    for key, title, color, filename in ck_metrics:
        save_graph(
            ck_versions_in_order,
            [all_ck[v][key] for v in ck_versions_in_order],
            title, key.replace("avg_", "").upper(), color, filename, graphs_dir,
        )

    if ck_versions_in_order:
        save_overlay_graph(
            [
                (ck_versions_in_order, [all_ck[v]["avg_wmc"]  for v in ck_versions_in_order], "Avg WMC",  "steelblue"),
                (ck_versions_in_order, [all_ck[v]["avg_rfc"]  for v in ck_versions_in_order], "Avg RFC",  "mediumpurple"),
                (ck_versions_in_order, [all_ck[v]["avg_cbo"]  for v in ck_versions_in_order], "Avg CBO",  "crimson"),
                (ck_versions_in_order, [all_ck[v]["avg_lcom"] for v in ck_versions_in_order], "Avg LCOM", "darkorange"),
            ],
            "CK Metrics Overlaid (normalised per metric)",
            "ck_overlay.png",
            graphs_dir,
            legend_loc="lower right",
        )

    # SourceMeter — Code Clone graphs
    sm_versions = sorted(
        [p.stem for p in sm_dir.glob("*.json")],
        key=version_sort_key,
    )
    if sm_versions:
        def sm(v: str, *keys: str) -> float:
            data = json.loads((sm_dir / f"{v}.json").read_text())
            node = data
            for k in keys:
                node = node[k]
            return float(node)

        clone_graphs = [
            ("clone_classes",   "Clone Classes over Releases",   "Clone Classes",   "teal",      "sm_clone_classes.png"),
            ("clone_instances", "Clone Instances over Releases", "Clone Instances", "slategray", "sm_clone_instances.png"),
            ("clone_lloc",      "Cloned LLOC over Releases",     "Cloned LLOC",     "firebrick", "sm_clone_lloc.png"),
        ]
        for key, title, ylabel, color, filename in clone_graphs:
            save_graph(
                sm_versions,
                [sm(v, "clone_metrics", key) for v in sm_versions],
                title, ylabel, color, filename, graphs_dir,
            )

        cr_pairs = [(v, load_sm_cr(v)) for v in sm_versions]
        cr_versions = [v for v, cr in cr_pairs if cr is not None]
        cr_values   = [cr for _, cr in cr_pairs if cr is not None]

        if cr_versions:
            save_graph(
                cr_versions, cr_values,
                "Clone Ratio over Releases — SourceMeter",
                "Clone Ratio (%)", "darkorchid", "sm_clone_ratio.png", graphs_dir,
            )

            cr_v34_cutoff = Version("3.4")
            cr_v34_pairs = [(v, c) for v, c in zip(cr_versions, cr_values)
                            if version_sort_key(v) >= cr_v34_cutoff]
            if cr_v34_pairs:
                cr_v34_versions, cr_v34_values = zip(*cr_v34_pairs)
                save_graph(
                    list(cr_v34_versions), list(cr_v34_values),
                    "Clone Ratio over Releases (v3.4+) — SourceMeter",
                    "Clone Ratio (%)", "darkorchid", "sm_clone_ratio_v34plus.png", graphs_dir,
                )

        save_subplot_graph(
            [
                (sm_versions, [sm(v, "clone_metrics", "clone_classes")   for v in sm_versions], "Clone Classes",   "teal"),
                (sm_versions, [sm(v, "clone_metrics", "clone_instances") for v in sm_versions], "Clone Instances", "slategray"),
                (sm_versions, [sm(v, "clone_metrics", "clone_lloc")      for v in sm_versions], "Cloned LLOC",     "firebrick"),
            ],
            "Code Clone Metrics over Releases — SourceMeter",
            "sm_overlay.png",
            graphs_dir,
        )

        tlloc_pairs = [(v, load_sm_tlloc(v)) for v in sm_versions]
        tlloc_versions = [v for v, t in tlloc_pairs if t is not None]
        tlloc_values   = [t for _, t in tlloc_pairs if t is not None]

        if tlloc_versions:
            save_graph(
                tlloc_versions, tlloc_values,
                "Total Logical Lines of Code over Releases — SourceMeter",
                "TLLOC", "steelblue", "sm_tlloc.png", graphs_dir,
            )

            if cr_versions:
                # Align to versions present in both series
                cr_lookup = dict(zip(cr_versions, cr_values))
                dual_versions = [v for v in tlloc_versions if v in cr_lookup]
                dual_tlloc    = [tlloc_values[tlloc_versions.index(v)] for v in dual_versions]
                dual_cr       = [cr_lookup[v] for v in dual_versions]

                save_dual_axis_graph(
                    versions=dual_versions,
                    left_values=dual_tlloc,
                    left_label="Total LLOC",
                    left_color="steelblue",
                    right_values=dual_cr,
                    right_label="Clone Ratio (%)",
                    right_color="darkorchid",
                    title="Total LLOC vs Clone Ratio over Releases — SourceMeter",
                    filename="sm_tlloc_vs_clone_ratio.png",
                    graphs_dir=graphs_dir,
                )

                v34_cutoff = Version("3.4")
                dual_v34 = [(v, t, c) for v, t, c in zip(dual_versions, dual_tlloc, dual_cr)
                            if version_sort_key(v) >= v34_cutoff]
                if dual_v34:
                    d_versions, d_tlloc, d_cr = zip(*dual_v34)
                    save_dual_axis_graph(
                        versions=list(d_versions),
                        left_values=list(d_tlloc),
                        left_label="Total LLOC",
                        left_color="steelblue",
                        right_values=list(d_cr),
                        right_label="Clone Ratio (%)",
                        right_color="darkorchid",
                        title="Total LLOC vs Clone Ratio over Releases (v3.4+) — SourceMeter",
                        filename="sm_tlloc_vs_clone_ratio_v34plus.png",
                        graphs_dir=graphs_dir,
                    )

    # Overlay graph: all key metrics normalised onto one chart
    overlay_series: list[tuple[list[str], list[float], str, str]] = [
        (
            versions_in_order_of_release,
            [all_instabilities[v] for v in versions_in_order_of_release],
            "Instability",
            "steelblue",
        ),
        (
            versions_in_order_of_release,
            [all_cbo[v] for v in versions_in_order_of_release],
            "Avg CBO (fan-out)",
            "crimson",
        ),
        (
            versions_in_order_of_release,
            [all_rfc[v] for v in versions_in_order_of_release],
            "Avg RFC (fan-in+out)",
            "teal",
        ),
        (
            versions_in_order_of_release,
            [all_mq[v] for v in versions_in_order_of_release],
            "MQ (1 − CF)",
            "forestgreen",
        ),
    ]
    if ck_versions_in_order:
        overlay_series += [
            (ck_versions_in_order, [all_ck[v]["avg_wmc"]  for v in ck_versions_in_order], "CK Avg WMC",  "mediumpurple"),
            (ck_versions_in_order, [all_ck[v]["avg_lcom"] for v in ck_versions_in_order], "CK Avg LCOM", "darkorange"),
        ]
    if sm_versions:
        overlay_series += [
            (sm_versions, [sm(v, "clone_metrics", "clone_classes")   for v in sm_versions], "SM Clone Classes",   "teal"),  # pyright: ignore[reportPossiblyUnboundVariable]
            (sm_versions, [sm(v, "clone_metrics", "clone_instances") for v in sm_versions], "SM Clone Instances", "slategray"),  # pyright: ignore[reportPossiblyUnboundVariable]
            (sm_versions, [sm(v, "clone_metrics", "clone_lloc")      for v in sm_versions], "SM Cloned LLOC",     "firebrick"),  # pyright: ignore[reportPossiblyUnboundVariable]
        ]
    save_overlay_graph(
        overlay_series,
        "All Metrics Overlaid (normalised per metric)",
        "overlay_all.png",
        graphs_dir,
    )
