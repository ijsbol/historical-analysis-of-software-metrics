from pathlib import Path

ROOT = Path(__file__).parent
VERSIONS_DIR = ROOT / "versions"
DEPS_DIR = ROOT / "deps"
CK_DIR = ROOT / "ck_metrics"


def iter_versions() -> list[tuple[str, Path]]:
    return [
        (p.name, p)
        for p in sorted(VERSIONS_DIR.iterdir(), key=lambda p: p.name)
        if p.is_dir()
    ]


def find_icalendar_src(version_dir: Path) -> Path | None:
    for candidate in (version_dir / "src" / "icalendar", version_dir / "icalendar"):
        if candidate.is_dir():
            return candidate
    return None
