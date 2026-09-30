"""Headless Blender converter: GLTF/GLB -> FBX.

Run as:
    blender.exe -b --python blender_convert.py -- <input> <output>

Exit codes:
    0  success
    2  missing arguments
    3  input file not found
    4  conversion error
    5  output file was not created
"""

import os
import sys

try:
    import bpy
except ImportError:
    sys.stderr.write("ERROR: this script must be run inside Blender\n")
    sys.exit(1)

LN_PREFIX_OK = "OK:"
LN_PREFIX_ERR = "ERROR:"
LN_PREFIX_MISSING = "MISSING:"


def parse_args(argv):
    args = list(argv)
    if "--" in args:
        args = args[args.index("--") + 1:]
    if not args:
        return None, None
    src = args[0]
    dst = args[1] if len(args) > 1 else ""
    src = os.path.abspath(src)
    dst = os.path.abspath(dst) if dst else ""
    return src, dst


def reset_scene():
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    except Exception:
        pass
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_source(src):
    ext = os.path.splitext(src)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=src)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=src)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=src)
    elif ext == ".blend":
        with bpy.data.libraries.load(src) as (data_from, data_to):
            data_to.objects = [n for n in data_from.objects]
            for obj in data_to.objects:
                if obj is not None:
                    bpy.context.scene.collection.objects.link(obj)
    else:
        raise ValueError("Unsupported format: {}".format(ext))


def export_fbx(dst):
    kwargs = dict(
        filepath=dst,
        check_existing=False,
        use_selection=False,
        use_mesh_modifiers=True,
        use_armature_deform_only=True,
        add_leaf_bones=False,
        object_types={"EMPTY", "CAMERA", "LIGHT", "ARMATURE", "MESH", "OTHER"},
        apply_unit_scale=True,
        apply_scale="FBX_UNITS",
        mesh_smooth_type="FACE",
        embed_textures=True,
    )
    try:
        bpy.ops.export_scene.fbx(**kwargs)
    except TypeError as err:
        msg = str(err)
        for key in ("apply_scale", "mesh_smooth_type", "embed_textures",
                    "use_armature_deform_only", "add_leaf_bones",
                    "object_types", "apply_unit_scale"):
            if key in msg:
                kwargs.pop(key, None)
        bpy.ops.export_scene.fbx(**kwargs)


def main():
    src, dst = parse_args(sys.argv)
    if not src or not dst:
        print(LN_PREFIX_ERR + "missing input/output arguments")
        return 2
    if not os.path.isfile(src):
        print(LN_PREFIX_MISSING + src)
        return 3

    out_dir = os.path.dirname(dst)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    try:
        reset_scene()
        import_source(src)
        export_fbx(dst)
    except Exception as exc:
        print(LN_PREFIX_ERR + str(exc))
        return 4

    if os.path.isfile(dst):
        print(LN_PREFIX_OK + dst)
        return 0
    print(LN_PREFIX_ERR + "output file was not created: " + dst)
    return 5


if __name__ == "__main__":
    sys.exit(main())