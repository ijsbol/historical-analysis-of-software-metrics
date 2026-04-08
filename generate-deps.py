import subprocess

from utils import DEPS_DIR, find_icalendar_src, iter_versions


def main() -> None:
    DEPS_DIR.mkdir(exist_ok=True)

    for version, version_dir in iter_versions():
        output = DEPS_DIR / f"v{version}.json"

        if output.exists():
            print(f"  exists  v{version}")
            continue

        src = find_icalendar_src(version_dir)
        if src is None:
            print(f"  skip    {version} (no icalendar package found)")
            continue

        print(f"  running {version}")
        result = subprocess.run(
            [
                "pydeps",
                str(src),
                "--show-deps",
                "--noshow",
                "--only", "icalendar",
                "--deps-output", str(output),
                "--no-output",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR   {version}:\n{result.stderr.strip()}")

    print("Done.")


if __name__ == "__main__":
    main()
