#!/usr/bin/env bash
#
# Convert a DeepMotion FBX export into a Mixamo-compatible FBX, ready to
# drop into VirtualChat's backend/output/gestures/ or poses/ folder.
#
# Usage:
#   ./convert.sh [input.fbx] [output.fbx]
#
# Defaults:
#   input.fbx   input/notworking.fbx
#   output.fbx  output/final_mixamo_animation.fbx

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONVERTER="$SCRIPT_DIR/src/convert_deepmotion.py"

usage() {
  cat <<EOF
Usage: $(basename "$0") [input.fbx] [output.fbx]

  input.fbx    DeepMotion FBX export to convert.
               Default: input/notworking.fbx
  output.fbx   Where to write the converted, Mixamo-compatible file.
               Default: output/final_mixamo_animation.fbx

Examples:
  $(basename "$0")
  $(basename "$0") input/my_take.fbx output/wave.fbx
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

INPUT="${1:-input/notworking.fbx}"
OUTPUT="${2:-output/final_mixamo_animation.fbx}"

if ! command -v blender >/dev/null 2>&1; then
  echo "error: 'blender' isn't on PATH. Install Blender (4.4+; tested on 5.2 LTS) and try again." >&2
  exit 1
fi

if [[ ! -f "$INPUT" ]]; then
  echo "error: input file not found: $INPUT" >&2
  exit 1
fi

if [[ ! -f "$CONVERTER" ]]; then
  echo "error: converter script not found at $CONVERTER" >&2
  exit 1
fi

echo "Converting:"
echo "  input:  $INPUT"
echo "  output: $OUTPUT"
echo

blender \
  --factory-startup \
  --background \
  --python "$CONVERTER" \
  -- "$INPUT" "$OUTPUT"

echo
echo "DONE: $OUTPUT"
