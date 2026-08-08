#!/usr/bin/env python3
"""
Convert a DeepMotion FBX export into a Mixamo-compatible FBX: armature +
baked animation only, bones renamed to the mixamorig: convention, ready to
drop into VirtualChat's backend/output/gestures/<tag>.fbx.

Why the bone rename matters:
VirtualChat's frontend (loadMixamoAnimation.js) retargets clips onto the
VRM avatar using three-vrm's mixamoVRMRigMap, which looks up bones by the
exact string "mixamorig:Hips", "mixamorig:Spine", etc. Real Mixamo
downloads already carry that prefix. DeepMotion's export does not, so
without this rename step the retargeter finds zero matching bones and the
clip silently no-ops (falls back to the procedural pose in the app).

Why we bake the animation:
Real Mixamo clips are dense, per-frame baked keyframes. DeepMotion's mocap
curves are already near-continuous, but leaving them as sparse
Bezier-interpolated F-curves asks three.js's FBXLoader to reproduce
Blender's curve evaluation, which it does not do faithfully (it does
linear interpolation between whatever keys are actually in the file).
Baking removes that mismatch and matches the format the app already
handles fine.
"""

import bpy
import sys
import os
import io
import contextlib


MIXAMO_PREFIX = "mixamorig:"

# DeepMotion names bones like "l_handThumb1_JNT" - a different vocabulary
# entirely from Mixamo's "mixamorig:LeftHandThumb1", not just a missing
# prefix. Confirmed from an actual DeepMotion export (52 bones, 0 already
# mixamorig:-prefixed): hips_JNT, spine_JNT, spine1_JNT, spine2_JNT,
# neck_JNT, head_JNT, l_/r_ shoulder/arm/forearm/hand_JNT, l_/r_
# hand{Thumb,Index,Middle,Ring,Pinky}{1,2,3}_JNT. Legs weren't visible in
# the log (cut off at bone 40 of 52) so upLeg/leg/foot/toeBase below are
# the standard-rig equivalent but unverified against this export - if
# they're wrong, normalize_bone_names() below will say so explicitly
# instead of silently mis-mapping them.
#
# Keys are normalized (lowercased, non-alphanumeric stripped) so DeepMotion's
# inconsistent internal casing - e.g. "forearm" all lowercase but
# "handThumb1" camelCase - can't cause a silent mismatch against Mixamo's
# actual casing ("ForeArm").
_MIXAMO_CANONICAL = {
    "hips": "Hips",
    "spine": "Spine",
    "spine1": "Spine1",
    "spine2": "Spine2",
    "neck": "Neck",
    "head": "Head",
    "shoulder": "Shoulder",
    "arm": "Arm",
    "forearm": "ForeArm",
    "hand": "Hand",
    "handthumb1": "HandThumb1",
    "handthumb2": "HandThumb2",
    "handthumb3": "HandThumb3",
    "handindex1": "HandIndex1",
    "handindex2": "HandIndex2",
    "handindex3": "HandIndex3",
    "handmiddle1": "HandMiddle1",
    "handmiddle2": "HandMiddle2",
    "handmiddle3": "HandMiddle3",
    "handring1": "HandRing1",
    "handring2": "HandRing2",
    "handring3": "HandRing3",
    "handpinky1": "HandPinky1",
    "handpinky2": "HandPinky2",
    "handpinky3": "HandPinky3",
    # legs - unverified, see note above
    "upleg": "UpLeg",
    "leg": "Leg",
    "foot": "Foot",
    "toebase": "ToeBase",
    # extra aliases, purely a hedge in case DeepMotion's leg names use
    # different words than its upper-body ones
    "thigh": "UpLeg",
    "upperleg": "UpLeg",
    "calf": "Leg",
    "lowerleg": "Leg",
    "shin": "Leg",
    "toe": "ToeBase",
    "ball": "ToeBase",
}


def _normalize_key(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def deepmotion_to_mixamo_name(name):
    """
    Map one DeepMotion '..._JNT' bone name to its Mixamo equivalent
    (without the mixamorig: prefix - that's added by the caller).
    Returns None if it can't be confidently matched, rather than guessing.
    """
    base = name[:-len("_JNT")] if name.endswith("_JNT") else name

    side = ""
    remainder = base
    if base.startswith("l_"):
        side, remainder = "Left", base[2:]
    elif base.startswith("r_"):
        side, remainder = "Right", base[2:]

    canonical = _MIXAMO_CANONICAL.get(_normalize_key(remainder))
    if canonical is None:
        return None

    return side + canonical


def clear_scene():
    # Data-API removal instead of the select_all/delete operator pair.
    # Equivalent result, but it doesn't depend on an active view layer
    # existing, which is the safer assumption to make in --background runs.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_fbx(filepath):
    print("IMPORTING:", filepath)

    # DeepMotion embeds a 16-bit "Short" custom property per bone that
    # Blender's FBX importer can't map to a Python custom property. It
    # prints one identical warning line per bone (harmless - doesn't
    # affect the skeleton or animation) which just buries real output.
    # Filtered here rather than blanket-silencing the whole import, so
    # anything else the importer says still gets through.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bpy.ops.import_scene.fbx(
            filepath=filepath,
            use_anim=True
        )

    suppressed = 0
    for line in buf.getvalue().splitlines():
        if "User property type" in line and "is not supported" in line:
            suppressed += 1
            continue
        print(line)

    if suppressed:
        print(f"(suppressed {suppressed} harmless 'User property type ... "
              f"is not supported' warnings from DeepMotion's per-bone metadata)")


def remove_meshes():
    for obj in list(bpy.data.objects):
        if obj.type == "MESH":
            print("REMOVING MESH:", obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)


def remove_non_armature_objects():
    for obj in list(bpy.data.objects):
        if obj.type not in {"ARMATURE"}:
            bpy.data.objects.remove(obj, do_unlink=True)


def get_armature():
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            return obj

    raise RuntimeError("No armature found")


def normalize_bone_names(armature):
    """
    Force every bone onto the mixamorig:<Name> convention.
    Renaming armature.data.bones[i].name also renames the matching
    pose bone and Blender automatically fixes up any F-curve data_paths
    that reference pose.bones["OldName"], so animation stays attached.
    """
    renamed = []
    already_ok = []
    unmapped = []

    for bone in armature.data.bones:
        name = bone.name

        if name.startswith(MIXAMO_PREFIX):
            already_ok.append(name)
            continue

        mixamo_name = deepmotion_to_mixamo_name(name)

        if mixamo_name is None:
            unmapped.append(name)
            continue

        new_name = MIXAMO_PREFIX + mixamo_name
        bone.name = new_name
        renamed.append((name, new_name))

    print(f"BONES ALREADY 'mixamorig:'-PREFIXED: {len(already_ok)}")
    print(f"BONES RENAMED: {len(renamed)}")
    for old, new in renamed:
        print(f"  {old}  ->  {new}")

    if unmapped:
        print(f"BONES THAT COULD NOT BE CONFIDENTLY MAPPED: {len(unmapped)}")
        for name in unmapped:
            print(f"  UNMAPPED: {name}")
        raise RuntimeError(
            "Some bones didn't match the known Mixamo naming table (see "
            "UNMAPPED list above). Stopping instead of exporting a file "
            "that would silently fail to retarget - send these names back "
            "and the table can be extended."
        )

    return renamed, already_ok, unmapped


def prepare_animation(armature):
    print("ARMATURE:", armature.name)

    anim_data = armature.animation_data
    if not anim_data:
        raise RuntimeError("No animation data")

    action = anim_data.action
    if not action:
        raise RuntimeError("No action found")

    print("ACTION:", action.name)
    print("RANGE:", action.frame_range)

    # Blender 4.4+ Slotted Actions: an object is bound to the action AND
    # to a specific slot inside it. Import binds this correctly, but we
    # defensively re-check before export in case anything upstream left
    # the slot unset (this is a no-op on Blender versions without slots).
    if hasattr(anim_data, "action_slot") and not anim_data.action_slot:
        suitable = list(getattr(anim_data, "action_suitable_slots", []))
        if suitable:
            anim_data.action_slot = suitable[0]
            print("REBOUND ACTION SLOT:", suitable[0].name_display)
        else:
            raise RuntimeError(
                "Action has no slot suitable for this armature - "
                "animation exists but isn't bound to it"
            )

    start, end = action.frame_range
    # round() rather than int() - truncation was quietly dropping the
    # fractional tail of the range (e.g. 455.9955 -> 455, losing a frame)
    bpy.context.scene.frame_start = int(round(start))
    bpy.context.scene.frame_end = int(round(end))

    for track in list(anim_data.nla_tracks):
        anim_data.nla_tracks.remove(track)

    # Cheap safety net - re-affirm the binding. No-op if already correct.
    anim_data.action = action

    return action


def export_fbx(filepath, armature, action):
    print("EXPORT:", filepath)

    # VirtualChat's loadMixamoAnimation.js (adapted from pixiv/three-vrm's
    # official example) does:
    #   THREE.AnimationClip.findByName(asset.animations, 'mixamo.com')
    # findByName() returns null if nothing matches, and the next line
    # blindly does clip.tracks.forEach(...) - crashing with exactly
    # "Cannot read properties of null (reading 'tracks')" if the take
    # isn't named that. Real Mixamo/Maya exports always name their take
    # "mixamo.com"; Blender's FBX exporter names it after the *scene*
    # instead ("Scene" by default), so we rename the scene to match.
    bpy.context.scene.name = "mixamo.com"

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature

    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=True,
        object_types={"ARMATURE"},
        add_leaf_bones=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",

        # Bake to dense per-frame keys (see module docstring for why).
        # use_all_bones=False matters a lot for file size: True forces
        # every bone (including ones DeepMotion never animated, e.g.
        # fingers/toes) to get baked Translation+Rotation+Scale curves
        # regardless. False only bakes bones that already carry motion,
        # which is what real Mixamo/Maya-exported clips look like too.
        bake_anim=True,
        bake_anim_use_all_bones=False,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
    )


def main():
    if "--" not in sys.argv:
        sys.exit(1)

    args = sys.argv[sys.argv.index("--") + 1:]

    if len(args) != 2:
        raise RuntimeError("Usage: input.fbx output.fbx")

    input_file = args[0]
    output_file = args[1]

    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    clear_scene()
    import_fbx(input_file)
    remove_meshes()
    remove_non_armature_objects()

    armature = get_armature()
    normalize_bone_names(armature)
    action = prepare_animation(armature)

    export_fbx(output_file, armature, action)

    print("DONE")
    print(output_file)


if __name__ == "__main__":
    main()
