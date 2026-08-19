from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ANALYZER_KEY = "package-api-surface"
ANALYZER_VERSION = "1.0.0"
CHECKSUM = re.compile(r"^sha256:[a-f0-9]{64}$")
JS_EXPORT = re.compile(
    r"(?:export\s+(?:declare\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?P<kind>function|class|const|let|var|interface|type|enum)\s+"
    r"|exports\.)(?P<name>[A-Za-z_$][\w$]*)"
)
JS_EXPORT_LIST = re.compile(r"export\s*\{(?P<symbols>[^}]+)\}")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_key(*parts: object) -> str:
    payload = "\x1f".join(part if isinstance(part, str) else canonical_json(part) for part in parts)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ApiSymbol:
    module: str
    name: str
    kind: str

    def as_dict(self) -> dict[str, str]:
        return {"module": self.module, "name": self.name, "kind": self.kind}


def analyze_artifact(
    root: Path,
    *,
    ecosystem: str,
    package_purl: str,
    artifact_checksum: str,
    max_files: int = 10_000,
    max_bytes: int = 100 * 1024 * 1024,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("artifact root must be an existing directory")
    if ecosystem not in {"npm", "pypi"}:
        raise ValueError("ecosystem must be npm or pypi")
    if not package_purl.startswith(f"pkg:{ecosystem}/") or "@" not in package_purl:
        raise ValueError("package_purl must identify an exact version")
    if not CHECKSUM.fullmatch(artifact_checksum):
        raise ValueError("artifact_checksum must be a sha256 key")
    if max_files <= 0 or max_bytes <= 0:
        raise ValueError("artifact limits must be positive")

    symbols: set[ApiSymbol] = set()
    limitations: list[str] = []
    files_scanned = 0
    bytes_read = 0
    truncated = False
    candidates = sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    for path in candidates:
        suffix = path.suffix.lower()
        if ecosystem == "npm" and suffix not in {".js", ".mjs", ".cjs", ".ts", ".d.ts"}:
            continue
        if ecosystem == "pypi" and suffix != ".py":
            continue
        size = path.stat().st_size
        if files_scanned >= max_files or bytes_read + size > max_bytes:
            truncated = True
            continue
        relative = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8", errors="replace")
        files_scanned += 1
        bytes_read += size
        if ecosystem == "npm":
            symbols.update(_javascript_symbols(relative, content))
        else:
            try:
                symbols.update(_python_symbols(relative, ast.parse(content, filename=relative)))
            except SyntaxError:
                limitations.append(f"could not parse {relative}")
    if truncated:
        limitations.append("artifact file or byte limit reached")
    if ecosystem == "npm":
        limitations.append("runtime-generated exports and conditional export targets may be incomplete")
    else:
        limitations.append("dynamic __getattr__, extension modules, and runtime-generated exports may be incomplete")
    ordered = sorted(symbols, key=lambda item: (item.module, item.name, item.kind))
    fingerprint = sha256_key(
        artifact_checksum,
        ANALYZER_KEY,
        ANALYZER_VERSION,
        ecosystem,
        package_purl,
    )
    return {
        "api_surface_contract_version": "1.0.0",
        "package_purl": package_purl,
        "ecosystem": ecosystem,
        "artifact_checksum": artifact_checksum,
        "analyzer": {"key": ANALYZER_KEY, "version": ANALYZER_VERSION},
        "analysis_fingerprint": fingerprint,
        "public_symbol_count": len(ordered),
        "symbols": [symbol.as_dict() for symbol in ordered],
        "stats": {"files_scanned": files_scanned, "bytes_read": bytes_read},
        "completeness": "PARTIAL" if truncated else "COMPLETE",
        "limitations": sorted(set(limitations)),
    }


def _javascript_symbols(module: str, content: str) -> Iterable[ApiSymbol]:
    for match in JS_EXPORT.finditer(content):
        yield ApiSymbol(module, match.group("name"), match.group("kind") or "value")
    for match in JS_EXPORT_LIST.finditer(content):
        for item in match.group("symbols").split(","):
            value = item.strip().split(" as ")[-1].strip()
            if value:
                yield ApiSymbol(module, value, "re-export")


def _python_symbols(module: str, tree: ast.Module) -> Iterable[ApiSymbol]:
    explicit: set[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                values = {
                    item.value for item in node.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
                explicit = values
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            if (explicit is None and not name.startswith("_")) or (explicit is not None and name in explicit):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                yield ApiSymbol(module, name, kind)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if (explicit is None and not name.startswith("_")) or (explicit is not None and name in explicit):
                        yield ApiSymbol(module, name, "value")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract a checksum-keyed public package API surface")
    parser.add_argument("root", type=Path)
    parser.add_argument("--ecosystem", choices=("npm", "pypi"), required=True)
    parser.add_argument("--package-purl", required=True)
    parser.add_argument("--artifact-checksum", required=True)
    parser.add_argument("--max-files", type=int, default=10_000)
    parser.add_argument("--max-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = analyze_artifact(
            args.root,
            ecosystem=args.ecosystem,
            package_purl=args.package_purl,
            artifact_checksum=args.artifact_checksum,
            max_files=args.max_files,
            max_bytes=args.max_bytes,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 2
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
