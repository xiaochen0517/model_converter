"""DirectX ``.x`` -> glTF 2.0 binary (``.glb``) conversion via Blender.

Runs the local Blender installation headless. Blender 5.x ships the official
``io_directx_x`` importer (geometry, materials, armatures, skin weights and
animation) and the Khronos glTF 2.0 exporter, which writes spec-compliant
``.glb`` files with universally compatible component types (UBYTE joints,
USHORT indices). No third-party Python packages are required.

Requirements:
- Blender 5.x with the ``io_directx_x`` extension enabled (installed via
  Extensions in the UI; it lives in the user profile, not the install dir).
- ``blender.exe`` discoverable via ``BLENDER_EXE``, the default install
  path, other versions under the ``Blender Foundation`` directory, or
  ``PATH``.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "blender_bridge.py"

#: Default Blender 5.2 installation on this machine.
DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


class BlenderError(RuntimeError):
    """Raised when the Blender conversion fails."""


# --------------------------------------------------------------------------- #
# Blender discovery & invocation
# --------------------------------------------------------------------------- #
def find_blender() -> Path:
    """Locate the Blender executable.

    Search order: ``BLENDER_EXE`` environment variable, the default install
    path, other versions under the standard ``Blender Foundation`` directory,
    then ``PATH``.
    """
    candidates: list[Path] = []
    env = os.environ.get("BLENDER_EXE")
    if env:
        candidates.append(Path(env))
    candidates.append(DEFAULT_BLENDER)
    foundation = DEFAULT_BLENDER.parents[1]  # .../Blender Foundation
    if foundation.is_dir():
        candidates.extend(sorted(foundation.glob("Blender */blender.exe"), reverse=True))
    from_path = shutil.which("blender")
    if from_path:
        candidates.append(Path(from_path))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BlenderError(
        "blender.exe not found. Install Blender 5.x with the io_directx_x "
        "extension, or set the BLENDER_EXE environment variable."
    )


def convert_files(
    pairs: list[tuple[str | Path, str | Path]],
    timeout: int = 1800,
) -> dict[Path, str | None]:
    """Convert many ``.x`` files in a single Blender process.

    ``pairs`` is a list of ``(source, target)`` tuples. Returns a dict
    mapping each source to ``None`` on success or an error message.
    """
    blender_exe = find_blender()
    pairs = [(Path(s).resolve(), Path(t).resolve()) for s, t in pairs]
    for _src, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)

    manifest_fd, manifest_path = tempfile.mkstemp(prefix="x2glb_", suffix=".json")
    try:
        with os.fdopen(manifest_fd, "w", encoding="utf-8") as fh:
            json.dump([[str(s), str(t)] for s, t in pairs], fh)

        proc = subprocess.run(
            [str(blender_exe), "-b", "-P", str(_BRIDGE_SCRIPT), "--", manifest_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise BlenderError(
            f"could not run '{blender_exe}'. Set BLENDER_EXE to a valid blender.exe."
        ) from None
    finally:
        os.unlink(manifest_path)

    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-20:])
        raise BlenderError(
            f"blender exited with code {proc.returncode}:\n{tail}"
        )

    ok_sources = {
        Path(parts[1])
        for line in proc.stdout.splitlines()
        if line.startswith("BRIDGE_OK\t")
        and len(parts := line.split("\t", 2)) == 3
    }
    errors: dict[Path, str] = {
        Path(parts[1]): parts[2]
        for line in proc.stderr.splitlines()
        if line.startswith("BRIDGE_ERR\t")
        and len(parts := line.split("\t", 2)) == 3
    }

    results: dict[Path, str | None] = {}
    for src, _target in pairs:
        if src in errors:
            results[src] = errors[src]
        elif src in ok_sources:
            results[src] = None
        else:
            results[src] = "blender reported no status for this file"
    return results


def convert_x_to_glb(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """Convert a single ``.x`` file to ``.glb`` using Blender.

    If ``output_path`` is omitted, the ``.glb`` is written next to the input.
    Returns the path of the generated file.
    """
    source = Path(input_path).resolve()
    target = (Path(output_path) if output_path else source.with_suffix(".glb")).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    results = convert_files([(source, target)])
    error = results[source]
    if error:
        raise BlenderError(f"{source.name}: {error}")
    return target


# --------------------------------------------------------------------------- #
# glb inspection
# --------------------------------------------------------------------------- #
# glb chunk types (little-endian uint32 of the 4-byte ASCII tag).
_GLB_CHUNK_JSON = 0x4E4F534A  # b"JSON"


def inspect_glb(path: str | Path) -> dict[str, int]:
    """Return a summary of a ``.glb`` file by parsing its JSON chunk.

    This is a lightweight, dependency-free way to confirm the conversion kept
    meshes, skins and animations (``skins`` / ``animations`` counts).
    """
    data = Path(path).read_bytes()
    if len(data) < 12:
        raise ValueError(f"'{path}' is too small to be a glb file")

    magic, version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError(f"'{path}' is not a glb file (bad magic: {magic!r})")

    json_bytes: bytes | None = None
    offset = 12
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk_data = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == _GLB_CHUNK_JSON:
            json_bytes = chunk_data
            break

    if json_bytes is None:
        raise ValueError(f"'{path}' has no JSON chunk")

    gltf = json.loads(json_bytes.decode("utf-8"))
    return {
        "version": version,
        "meshes": len(gltf.get("meshes", [])),
        "nodes": len(gltf.get("nodes", [])),
        "materials": len(gltf.get("materials", [])),
        "skins": len(gltf.get("skins", [])),
        "animations": len(gltf.get("animations", [])),
        "textures": len(gltf.get("textures", [])),
        "images": len(gltf.get("images", [])),
        "accessors": len(gltf.get("accessors", [])),
        "buffers": len(gltf.get("buffers", [])),
    }
