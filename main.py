"""Command-line entry point for the DirectX ``.x`` -> ``.glb`` converter."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from converter import BlenderError, convert_files, inspect_glb


def _collect_inputs(paths: list[str]) -> list[tuple[Path, Path]]:
    """Expand directories into ``(source, rel_dir)`` pairs, recursively.

    ``rel_dir`` is the source's directory relative to its input directory
    root (``Path()`` for bare file inputs), so the output tree mirrors the
    source tree. Non-existent entries raise ``FileNotFoundError``.
    """
    files: list[tuple[Path, Path]] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found = sorted(
                p for p in path.rglob("*")
                if p.is_file() and p.suffix.lower() == ".x"
            )
            files.extend((p, p.parent.relative_to(path)) for p in found)
        elif path.is_file():
            files.append((path, Path()))
        else:
            raise FileNotFoundError(f"input not found: {path}")
    return files


def _copy_aux_files(roots: list[Path], output_dir: Path) -> list[tuple[Path, Path]]:
    """Copy non-``.x`` files from input directories into the output tree.

    Returns the ``(source, target)`` pairs that were copied.
    """
    copied: list[tuple[Path, Path]] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() != ".x":
                target = output_dir / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                copied.append((path, target))
    return copied


def _report(inspected: dict[str, int]) -> str:
    animation = inspected["animations"]
    skins = inspected["skins"]
    animation_note = (
        "yes"
        if animation
        else ("skinned (no clips)" if skins else "no")
    )
    return (
        f"meshes={inspected['meshes']} nodes={inspected['nodes']} "
        f"materials={inspected['materials']} skins={skins} "
        f"animations={animation} images={inspected['images']} "
        f"-> animation: {animation_note}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-converter",
        description="Convert DirectX .x model files to glTF 2.0 binary (.glb) via Blender.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input .x file(s) or directories containing .x files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output",
        help="Output directory for generated .glb files (default: ./output).",
    )
    parser.add_argument(
        "--non-x",
        choices=["ignore", "copy"],
        default="ignore",
        help="How to handle non-.x files found in input directories: "
        "'ignore' skips them (default), 'copy' copies them to the "
        "matching location in the output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        inputs = _collect_inputs(args.inputs)
        if not inputs:
            print("No .x files found for the given inputs.", file=sys.stderr)
            return 1

        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.non_x == "copy":
            roots = [Path(raw) for raw in args.inputs if Path(raw).is_dir()]
            for source, target in _copy_aux_files(roots, output_dir):
                print(f"[copy] {source} -> {target}")

        pairs = [
            (source, output_dir / rel_dir / f"{source.stem}.glb")
            for source, rel_dir in inputs
        ]
        results = convert_files(pairs)

        targets = {Path(s).resolve(): Path(t).resolve() for s, t in pairs}
        failures = 0
        for source, error in results.items():
            target = targets[source]
            if error:
                failures += 1
                print(f"[error] {source.name}: {error}", file=sys.stderr)
            else:
                summary = _report(inspect_glb(target))
                print(f"[ok] {source.name} -> {target}  ({summary})")

        return 1 if failures else 0
    except (BlenderError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
