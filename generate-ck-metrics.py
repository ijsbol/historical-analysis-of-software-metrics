import ast
import json
from pathlib import Path

from radon.complexity import cc_visit

from utils import CK_DIR, find_icalendar_src, iter_versions


def compute_lcom(class_node: ast.ClassDef) -> float:
    methods: list[set[str]] = []
    for node in ast.walk(class_node):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.args.args or node.args.args[0].arg != "self":
            continue
        attrs: set[str] = set()
        for n in ast.walk(node):
            if (
                isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id == "self"
            ):
                attrs.add(n.attr)
        methods.append(attrs)

    m = len(methods)
    if m <= 1:
        return 0.0
    all_attrs = set().union(*methods)
    a = len(all_attrs)
    if a == 0:
        return 0.0
    avg_methods_per_attr = sum(
        sum(1 for mset in methods if attr in mset) for attr in all_attrs
    ) / a
    return (m - avg_methods_per_attr) / (m - 1)


def compute_cbo(tree: ast.Module) -> int:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("icalendar"):
                    imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("icalendar"):
                imported.add(node.module)
    return len(imported)


def analyse_file(py_file: Path, module_name: str) -> list[dict]:
    source = py_file.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    cbo = compute_cbo(tree)

    # radon CC: index classes by name
    try:
        cc_results = {r.name: r for r in cc_visit(source) if hasattr(r, "methods")}
    except Exception:
        cc_results = {}

    records = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name = node.name
        cc_class = cc_results.get(name)
        if cc_class is not None:
            wmc = sum(m.complexity for m in cc_class.methods) or cc_class.complexity
            rfc = len(cc_class.methods)
        else:
            # fall back to counting method defs via AST
            method_nodes = [
                n for n in ast.walk(node)
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                and n.args.args and n.args.args[0].arg == "self"
            ]
            wmc = len(method_nodes)
            rfc = len(method_nodes)

        records.append({
            "class": name,
            "module": module_name,
            "wmc": wmc,
            "rfc": rfc,
            "cbo": cbo,
            "lcom": round(compute_lcom(node), 4),
        })
    return records


def analyse_version(src_dir: Path) -> list[dict]:
    records = []
    for py_file in sorted(src_dir.rglob("*.py")):
        rel = py_file.relative_to(src_dir.parent)
        module_name = ".".join(rel.with_suffix("").parts)
        records.extend(analyse_file(py_file, module_name))
    return records


def summarise(classes: list[dict]) -> dict:
    if not classes:
        return {"avg_wmc": 0, "avg_rfc": 0, "avg_cbo": 0, "avg_lcom": 0}
    n = len(classes)
    return {
        "avg_wmc":  round(sum(c["wmc"]  for c in classes) / n, 4),
        "avg_rfc":  round(sum(c["rfc"]  for c in classes) / n, 4),
        "avg_cbo":  round(sum(c["cbo"]  for c in classes) / n, 4),
        "avg_lcom": round(sum(c["lcom"] for c in classes) / n, 4),
    }


def main() -> None:
    CK_DIR.mkdir(exist_ok=True)

    for version, version_dir in iter_versions():
        output = CK_DIR / f"v{version}.json"

        if output.exists():
            print(f"  exists  v{version}")
            continue

        src = find_icalendar_src(version_dir)
        if src is None:
            print(f"  skip    {version} (no icalendar package found)")
            continue

        print(f"  analyse {version}")
        classes = analyse_version(src)
        result = {
            "version": version,
            "classes": classes,
            "summary": summarise(classes),
        }
        output.write_text(json.dumps(result, indent=2))

    print("Done.")


if __name__ == "__main__":
    main()
