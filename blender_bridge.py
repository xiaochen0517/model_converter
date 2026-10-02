"""Headless Blender bridge script (executed by ``blender.exe -b``).

Converts DirectX ``.x`` models to glTF 2.0 binary (``.glb``) in batch.

Invoked by :mod:`blender_backend` as::

    blender.exe -b -P blender_bridge.py -- <manifest.json>

The manifest is a JSON list of ``[source_path, target_path]`` pairs. Each job
runs in a fresh scene; a failing job is reported and does not abort the rest.

Per-job status lines are printed to stdout::

    BRIDGE_OK <TAB> <source> <TAB> <target>
    BRIDGE_ERR <TAB> <source> <TAB> <message>
"""

from __future__ import annotations

import json
import sys
import traceback

import bpy

# --------------------------------------------------------------------------- #
# Scene cleanup
# --------------------------------------------------------------------------- #
def clear_scene() -> None:
    """Remove every object and all orphaned data-blocks."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablocks in (
        bpy.data.actions,
        bpy.data.armatures,
        bpy.data.images,
        bpy.data.materials,
        bpy.data.meshes,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 250


# --------------------------------------------------------------------------- #
# Per-file conversion
# --------------------------------------------------------------------------- #
def convert(src: str, dst: str) -> None:
    bpy.ops.import_scene.directx_x(filepath=src)

    # Match the scene frame range to the imported animation(s), if any.
    ranges = [
        a.frame_range
        for a in bpy.data.actions
        if a.users and a.frame_range[1] > a.frame_range[0]
    ]
    if ranges:
        bpy.context.scene.frame_start = int(min(r[0] for r in ranges))
        bpy.context.scene.frame_end = int(max(r[1] for r in ranges))

    bpy.ops.export_scene.gltf(
        filepath=dst,
        export_format="GLB",
        use_selection=False,
        export_apply=False,
        export_animations=True,
        check_existing=False,
    )


def main() -> None:
    manifest_path = sys.argv[sys.argv.index("--") + 1]
    with open(manifest_path, encoding="utf-8") as fh:
        jobs = json.load(fh)

    clear_scene()
    for src, dst in jobs:
        try:
            convert(src, dst)
            print(f"BRIDGE_OK\t{src}\t{dst}", flush=True)
        except Exception as exc:  # noqa: BLE001 - keep the batch going
            print(f"BRIDGE_ERR\t{src}\t{exc}", flush=True)
            print(f"BRIDGE_ERR\t{src}\t{exc}", file=sys.stderr, flush=True)
            traceback.print_exc()
        finally:
            clear_scene()


main()
