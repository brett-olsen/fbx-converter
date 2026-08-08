# DeepMotion → Mixamo FBX Converter

Converts a [DeepMotion](https://www.deepmotion.com/) FBX motion-capture
export into a Mixamo-compatible FBX: armature + baked animation only,
bones renamed to Mixamo's `mixamorig:` convention, ready to retarget onto
a VRM avatar (e.g. via [pixiv/three-vrm](https://github.com/pixiv/three-vrm)'s
`humanoidAnimation` example, or any app built on it).

## Requirements

- [Blender](https://www.blender.org/) 4.4 or newer on your `PATH`
  (tested on 5.2 LTS)
- A DeepMotion FBX export as input

## Usage

```bash
./convert.sh input/take.fbx output/wave.fbx
```

With no arguments it defaults to `input/notworking.fbx` →
`output/final_mixamo_animation.fbx`.

## What it actually does

1. Imports the FBX, strips the mesh, keeps the armature + animation
2. Renames every bone from DeepMotion's naming (`hips_JNT`,
   `l_handThumb1_JNT`, ...) to Mixamo's (`mixamorig:Hips`,
   `mixamorig:LeftHandThumb1`, ...) — see [Bone mapping](#bone-mapping)
3. Bakes the animation to dense per-frame keyframes, matching how real
   Mixamo clips are structured
4. Names the animation take `mixamo.com`, matching what Mixamo's own
   exporter names it — see [Why the take is renamed](#why-the-take-is-renamed)
5. Exports armature-only, matching Mixamo's standard bone axes

It also transparently handles Blender 4.4+'s newer "Slotted Actions"
animation data model, so it works the same way on older and newer Blender
versions.

## Directory layout

```
convert.sh
src/
  convert_deepmotion.py   the converter Blender runs headlessly
  debug_animation.py      standalone inspection tool, see below
```

## Debugging a file

If a conversion fails or the output doesn't work, inspect the source
(or the output) directly:

```bash
blender --background --factory-startup --python src/debug_animation.py -- input/yourfile.fbx
```

Prints the action's frame range and slot binding, every NLA track, and
every bone name with its parent — including how many bones already use
the `mixamorig:` prefix. Useful for checking a new DeepMotion export
before assuming the bone-mapping table below still applies to it.

## Bone mapping

DeepMotion names bones like `l_handThumb1_JNT` — a different vocabulary
from Mixamo's `mixamorig:LeftHandThumb1`, not just a missing prefix. The
mapping table in `convert_deepmotion.py` was built from an actual
DeepMotion export (52 bones) and covers the whole body: spine, head,
arms, all five fingers per hand, and legs. Left/right (`l_`/`r_`) always
maps to `Left`/`Right`; the mapping is case-insensitive against
DeepMotion's own naming so inconsistent casing on their side (e.g.
`forearm` vs `handThumb1`) can't cause a silent mismatch.

If a bone doesn't match anything in the table, the script **stops and
prints an `UNMAPPED` list** rather than exporting a file that would
silently fail to retarget. If that happens on a new export, add the
raw name(s) to `_MIXAMO_CANONICAL` in `convert_deepmotion.py`.

## Notes on two non-obvious gotchas

Both of these looked fine in Blender and only showed up in the actual
retargeting app — worth knowing about if you're extending this further.

- **Why the take is renamed.** Real Mixamo/Maya-exported FBX files always
  name their animation take `mixamo.com`. Code adapted from three-vrm's
  official `humanoidAnimation` example (as most Mixamo→VRM retargeters
  are) does `THREE.AnimationClip.findByName(asset.animations, 'mixamo.com')`
  with no fallback — if the take isn't named exactly that, it gets back
  `null` and crashes on the next line. Blender's FBX exporter names the
  take after the *scene* instead (`Scene` by default), so the script
  renames the scene to `mixamo.com` before exporting.
- **Why bones get baked selectively.** `bake_anim_use_all_bones=True`
  bakes Translation+Rotation+Scale onto *every* bone, including ones
  DeepMotion never animated (fingers, toes) — this alone made an export
  ~3x larger than an equivalent real Mixamo file. `False` only bakes
  bones that already carry motion, which is what real Mixamo/Maya
  exports look like too.

## Known limitations

- Assumes a single armature and a single action in the input file
- The bone-mapping table matches one specific DeepMotion export preset;
  a different DeepMotion project/rig setting could use different names
  (see [Debugging a file](#debugging-a-file))
- Blender's exporter adds an extra `Armature` null node as the bone
  hierarchy's parent, which genuine Maya/Mixamo exports don't have. It
  hasn't caused problems in testing, but it's a real structural
  difference worth knowing about if something ever behaves oddly
