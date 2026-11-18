#!/usr/bin/env bash
# Build the Flash ebook site in dist/ from the original 10th_Anniversary.exe:
#
#   dist/book/        the files packed inside the exe (tools/extract_iebook.py): config.xml,
#                     the iebook engine main.swf (patched by tools/patch_main_swf.py), pages, music
#   dist/ruffle/      self-hosted Ruffle from the npm registry
#   dist/index.html   from web/
#
# Options: RUFFLE_VERSION=0.7.1
# Needs: bash, python3, curl, tar.
set -euo pipefail

RUFFLE_VERSION="${RUFFLE_VERSION:-0.7.1}"

HERE="$(cd "$(dirname "$0")" && pwd)"
EXE="$HERE/10th_Anniversary.exe"
DIST="$HERE/dist"
CACHE="$HERE/cache"        # Ruffle download, reused between runs

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

for tool in python3 curl tar; do
    command -v "$tool" >/dev/null || die "missing '$tool'"
done
[ -f "$EXE" ] || die "10th_Anniversary.exe is missing"
rm -rf "$DIST"
mkdir -p "$DIST" "$CACHE"

log "Extracting the book from 10th_Anniversary.exe"
python3 "$HERE/tools/extract_iebook.py" "$EXE" "$DIST/book"
# The engine's SharedObject name has characters Flash forbids; Ruffle refuses it without this.
python3 "$HERE/tools/patch_main_swf.py" "$DIST/book/main.swf"

log "Ruffle $RUFFLE_VERSION"
TGZ="$CACHE/ruffle-$RUFFLE_VERSION.tgz"
if [ ! -s "$TGZ" ]; then
    curl -fL --retry 3 -o "$TGZ.part" "https://registry.npmjs.org/@ruffle-rs/ruffle/-/ruffle-$RUFFLE_VERSION.tgz"
    mv "$TGZ.part" "$TGZ"
fi
rm -rf "$CACHE/ruffle"
mkdir -p "$CACHE/ruffle" "$DIST/ruffle"
tar -xzf "$TGZ" -C "$CACHE/ruffle"
(cd "$CACHE/ruffle/package" && cp ruffle.js ./*.wasm core.ruffle.*.js LICENSE_* "$DIST/ruffle/")

cp "$HERE/web/index.html" "$DIST/"
touch "$DIST/.nojekyll"    # GitHub Pages' Jekyll would drop book/_silent.mp3 and book/_copyright.swf

log "Done: dist/"
echo "Test: python3 -m http.server -d dist 8000, then open http://localhost:8000/"
