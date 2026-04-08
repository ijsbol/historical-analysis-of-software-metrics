import json
import subprocess
import sys
from pathlib import Path

from utils import find_icalendar_src, iter_versions

LCOM_DIR = Path(__file__).parent / "lcom_metrics"


def count_modules(src_dir: Path) -> int:
    return len(list(src_dir.rglob("*.py")))


def main() -> None:
    LCOM_DIR.mkdir(exist_ok=True)

    for version, version_dir in iter_versions():
        output = LCOM_DIR / f"v{version}.json"

        if output.exists():
            print(f"  exists  v{version}")
            continue

        src = find_icalendar_src(version_dir)
        if src is None:
            print(f"  skip    {version} (no icalendar package found)")
            continue

        print(f"  analyse {version}")
        result = subprocess.run(
            [
                sys.executable, "-m", "pylint",
                str(src),
                "--disable=all",
                "--enable=design",
                "--output-format=json2",
            ],
            capture_output=True,
            text=True,
        )

        try:
            data = json.loads(result.stdout)
            messages = data.get("messages", [])
        except json.JSONDecodeError:
            print(f"  ERROR   {version}: could not parse pylint output")
            continue

        module_count = count_modules(src)
        by_code: dict[str, int] = {}
        for msg in messages:
            code = msg.get("messageId", "?")
            by_code[code] = by_code.get(code, 0) + 1

        total = len(messages)
        output.write_text(json.dumps({
            "version": version,
            "warnings": messages,
            "summary": {
                "total_warnings": total,
                "module_count": module_count,
                "warnings_per_module": round(total / module_count, 4) if module_count else 0,
                "by_code": by_code,
            },
        }, indent=2))

    print("Done.")


if __name__ == "__main__":
    main()
