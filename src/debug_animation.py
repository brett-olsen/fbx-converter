"""
Usage:
  blender --background --factory-startup --python debug_animation.py -- yourfile.fbx

If no "-- file.fbx" is given, it just inspects whatever is already loaded
in the current Blender session (e.g. after File > Import manually).
"""

import bpy
import sys
import io
import contextlib


def import_if_requested():
    if "--" not in sys.argv:
        return
    args = sys.argv[sys.argv.index("--") + 1:]
    if not args:
        return
    filepath = args[0]
    print("IMPORTING FOR INSPECTION:", filepath)

    # See convert_deepmotion.py for why this filter exists - it's the
    # same harmless per-bone "Short" custom-property warning, filtered
    # rather than blanket-suppressed so real importer output still shows.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bpy.ops.import_scene.fbx(filepath=filepath, use_anim=True)

    suppressed = 0
    for line in buf.getvalue().splitlines():
        if "User property type" in line and "is not supported" in line:
            suppressed += 1
            continue
        print(line)

    if suppressed:
        print(f"(suppressed {suppressed} harmless 'User property type ... "
              f"is not supported' warnings from DeepMotion's per-bone metadata)")


import_if_requested()


print("\n# ACTIONS IN BLENDER")
print("====================")

for action in bpy.data.actions:
    print("ACTION:", action.name)
    print(" FRAME RANGE:", action.frame_range)
    print(" USERS:", action.users)

    # Blender 4.4+ Slotted Actions
    if hasattr(action, "slots"):
        print(" SLOTS:", len(action.slots))
        for slot in action.slots:
            print("  SLOT:", slot.name_display, "identifier:", slot.identifier)

    if hasattr(action, "layers"):
        print(" LAYERS:")
        for layer in action.layers:
            print("  LAYER:", layer.name)
            for strip in layer.strips:
                print("   STRIP:", strip.type)


print("\n# ARMATURES")
print("====================")

for obj in bpy.data.objects:
    if obj.type != "ARMATURE":
        continue

    print("ARMATURE:", obj.name)

    if obj.animation_data:
        ad = obj.animation_data
        print(" ACTIVE ACTION:", ad.action)

        if hasattr(ad, "action_slot"):
            print(" ACTION SLOT:", ad.action_slot)

        print(" NLA TRACKS:", len(ad.nla_tracks))
        for track in ad.nla_tracks:
            print(" TRACK:", track.name)
            for strip in track.strips:
                print("  STRIP:", strip.name, strip.frame_start, strip.frame_end)
    else:
        print(" NO animation data")

    bones = list(obj.data.bones)
    mixamo_prefixed = sum(1 for b in bones if b.name.startswith("mixamorig:"))

    print(f" BONE COUNT: {len(bones)}")
    print(f" -> {mixamo_prefixed}/{len(bones)} bones already use the 'mixamorig:' naming convention")
    print(" BONE NAMES (name -> parent), all bones:")
    for bone in bones:
        parent = bone.parent.name if bone.parent else "-"
        print(f"  {bone.name}  ->  {parent}")
