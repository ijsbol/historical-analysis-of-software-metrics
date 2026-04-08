import json
import sys
from pathlib import Path
from typing import TypedDict


class Results(TypedDict):
    module: str
    fan_in: int
    fan_out: int


def load_deps(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def calculate_metrics(deps: dict) -> list[Results]:
    results: list[Results] = []
    for name, info in deps.items():
        if "test" in name:
            continue
        imported_by: list[str] = [
            m for m in info.get("imported_by", [])
            if m != name and not "test" in m
        ]
        imports: list[str] = [
            m for m in info.get("imports", [])
            if m != name and not "test" in m
        ]
        results.append(Results(
            module=name,
            fan_in=len(imported_by),
            fan_out=len(imports),
        ))
    return results


def print_table(metrics: list[Results]) -> None:
    sorted_metrics: list[Results] = sorted(metrics, key=lambda r: r["fan_in"], reverse=True)
    col_width: int = max(len(r["module"]) for r in sorted_metrics)
    header: str = f"{'Module':<{col_width}}  {'Fan-In':>7}  {'Fan-Out':>8}"
    print(header)
    print("-" * len(header))
    for row in sorted_metrics:
        print(f"{row['module']:<{col_width}}  {row['fan_in']:>7}  {row['fan_out']:>8}")
    print("-" * len(header))
    print(f"{'':<{col_width}}  {'Fan-In':>7}  {'Fan-Out':>8}")
    t_fan_in: int = sum([v['fan_in'] for v in sorted_metrics])
    t_fan_out: int = sum([v['fan_out'] for v in sorted_metrics])
    print(f"{'Total':<{col_width}}  {str(t_fan_in):>7}  {str(t_fan_out):>8}")

    instabilities: list[float] = [
        v['fan_out'] / (v['fan_in'] + v['fan_out'])
        for v in sorted_metrics
        if v['fan_in'] + v['fan_out'] > 0
    ]
    avg_instability = sum(instabilities) / len(instabilities) if instabilities else 0
    print(f"Instability rate: {avg_instability:.4f} ({avg_instability*100:.1f}%)")


if __name__ == "__main__":
    deps_file: str | None = sys.argv[1] if len(sys.argv) > 1 else None
    assert deps_file is not None

    path = Path(deps_file)
    if not path.exists():
        print(f"File not found: {deps_file}")
        sys.exit(1)

    deps = load_deps(path)
    metrics = calculate_metrics(deps)
    print_table(metrics)
