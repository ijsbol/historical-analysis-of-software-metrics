import io
import json
import os
import tarfile
import urllib.request

PACKAGE = "icalendar"
VERSIONS_DIR = "versions"


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def main() -> None:
    data = fetch_json(f"https://pypi.org/pypi/{PACKAGE}/json")
    releases: dict[str, list[dict]] = data["releases"]

    for version, artifacts in releases.items():
        sdists = [a for a in artifacts if a["packagetype"] == "sdist"]
        if not sdists:
            print(f"  skip {version} (no sdist)")
            continue

        version_dir = os.path.join(VERSIONS_DIR, version)
        if os.path.exists(version_dir) and os.listdir(version_dir):
            print(f"  exists {version_dir}")
            continue

        url = sdists[0]["url"]
        print(f"  downloading {version}")
        try:
            with urllib.request.urlopen(url) as response:
                data_bytes = response.read()
            with tarfile.open(fileobj=io.BytesIO(data_bytes)) as tar:
                members = tar.getmembers()
                # strip the top-level directory (e.g. icalendar-5.0.0/)
                top = members[0].name.split("/")[0]
                for member in members:
                    member.name = member.name[len(top):].lstrip("/")
                    if not member.name:
                        continue
                    tar.extract(member, path=version_dir, filter="data")
        except Exception as e:
            print(f"  ERROR {version}: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
