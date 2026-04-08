# Requires Python 3.8: uv python install 3.8

import csv
import json
import subprocess
from pathlib import Path

from utils import find_icalendar_src, iter_versions

ROOT = Path(__file__).parent
SM_BIN = ROOT / "SourceMeter-10.2.0-x64-Linux/Python/AnalyzerPython"
SM_RESULTS = ROOT / "sm_results"
SM_METRICS = ROOT / "sm_metrics"

PYTHON_BIN = subprocess.run(
    ["uv", "python", "find", "3.8"], capture_output=True, text=True
).stdout.strip() or "/usr/bin/python3"


def run_analyzer(version: str, src_dir: Path) -> Path | None:
    rel_src = src_dir.relative_to(ROOT)
    rel_results = SM_RESULTS.relative_to(ROOT) / version

    result = subprocess.run(
        [
            str(SM_BIN),
            f"-projectBaseDir:{rel_src}",
            "-projectName:icalendar",
            f"-resultsDir:{rel_results}",
            "-pythonVersion:3",
            f"-pythonBinary:{PYTHON_BIN}",
            "-runPylint:false",
            "-runFaultHunter:false",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    results_dir = ROOT / rel_results
    dated_dirs = sorted((results_dir / "icalendar" / "python").glob("*"))
    if not dated_dirs:
        print(f"  ERROR   {version}: no output\n{result.stderr[-300:]}")
        return None
    return dated_dirs[-1]


def read_csv(csv_file: Path, *columns: str) -> list[dict]:
    if not csv_file.exists():
        return []
    rows = []
    with csv_file.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, quotechar='"'):
            entry = {}
            for col in columns:
                try:
                    entry[col] = float(row[col])
                except (ValueError, KeyError, TypeError):
                    pass
            if entry:
                rows.append(entry)
    return rows


def avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def read_summary_metric(dated_dir: Path, name: str) -> float | None:
    summary_path = dated_dir / "icalendar-summary.json"
    if not summary_path.exists():
        return None
    data = json.loads(summary_path.read_text())
    for attr in data["nodes"][0]["attributes"]:
        if attr["name"] == name:
            return float(attr["value"])
    return None


def parse_output(dated_dir: Path) -> dict:
    class_rows = read_csv(dated_dir / "icalendar-Class.csv", "WMC", "LCOM5", "CBO", "RFC")
    clone_class_rows = read_csv(dated_dir / "icalendar-CloneClass.csv", "CI", "CLLOC")
    clone_inst_rows = read_csv(dated_dir / "icalendar-CloneInstance.csv", "CLLOC")

    cr_raw = read_summary_metric(dated_dir, "CR")
    clone_ratio = round(cr_raw * 100, 4) if cr_raw is not None else None  # as percentage

    clone_metrics: dict = {
        "clone_classes":   len(clone_class_rows),
        "clone_instances": int(sum(r.get("CI", 0) for r in clone_class_rows)),
        "clone_lloc":      int(sum(r.get("CLLOC", 0) for r in clone_inst_rows)),
    }
    if clone_ratio is not None:
        clone_metrics["clone_ratio"] = clone_ratio

    return {
        "class_metrics": {
            "avg_wmc":   avg([r["WMC"]   for r in class_rows if "WMC"   in r]),
            "avg_lcom5": avg([r["LCOM5"] for r in class_rows if "LCOM5" in r]),
            "avg_cbo":   avg([r["CBO"]   for r in class_rows if "CBO"   in r]),
            "avg_rfc":   avg([r["RFC"]   for r in class_rows if "RFC"   in r]),
        },
        "clone_metrics": clone_metrics,
    }


def main() -> None:
    SM_RESULTS.mkdir(exist_ok=True)
    SM_METRICS.mkdir(exist_ok=True)

    for version, version_dir in iter_versions():
        output = SM_METRICS / f"v{version}.json"
        if output.exists():
            print(f"  exists  v{version}")
            continue

        src = find_icalendar_src(version_dir)
        if src is None:
            print(f"  skip    {version} (no icalendar package found)")
            continue

        print(f"  analyse {version}")
        dated_dir = run_analyzer(version, src)
        if dated_dir is None:
            continue

        metrics = parse_output(dated_dir)
        output.write_text(json.dumps({"version": version, **metrics}, indent=2))

    print("Done.")


if __name__ == "__main__":
    main()
