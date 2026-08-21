"""Materialize a real multi-route React application from admitted product/design IR."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .real_app_design import canonical


@dataclass(frozen=True, slots=True)
class RealAppRenderReceipt:
    renderer: str
    manifest_sha256: str
    design_ir_sha256: str
    output_sha256: str
    files: Mapping[str, str]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _tree(root: Path) -> dict[str, str]:
    ignored = {"node_modules", "__pycache__", ".pytest_cache", "dist"}
    return {
        path.relative_to(root).as_posix(): _sha(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not ignored.intersection(path.parts)
        and path.suffix not in {".map", ".pyc", ".sqlite3"}
    }


def materialize_real_app(*, template: Path, output: Path, manifest: Mapping[str, Any], design_ir: Mapping[str, Any]) -> RealAppRenderReceipt:
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(
        template,
        output,
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", "dist", "*.pyc", "*.sqlite3"),
    )
    base = template.parent / "react-vite"
    for relative in ("package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts"):
        shutil.copy2(base / relative, output / relative)
    generated = output / "src" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "product.json").write_bytes(canonical(manifest) + b"\n")
    (generated / "design-ir.json").write_bytes(canonical(design_ir) + b"\n")
    files = _tree(output)
    output_sha = _sha(canonical(files))
    receipt = RealAppRenderReceipt(
        "luxeron.real-app-react.v1",
        _sha(canonical(manifest)),
        _sha(canonical(design_ir)),
        output_sha,
        files,
    )
    (output / "RENDER_RECEIPT.json").write_bytes(canonical({
        "renderer": receipt.renderer,
        "manifest_sha256": receipt.manifest_sha256,
        "design_ir_sha256": receipt.design_ir_sha256,
        "output_sha256": receipt.output_sha256,
        "files": receipt.files,
    }) + b"\n")
    return receipt
