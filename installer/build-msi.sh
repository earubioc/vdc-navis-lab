#!/usr/bin/env bash
# Builds the add-in MSI for one major version of Navisworks Manage.
#   installer/build-msi.sh <year> <version> <path to VdcNavisLab.dll compiled for that year> [out dir]
# Needs wixl and msitools (apt install wixl msitools). It does not need Windows or WiX.
# The GUIDs are derived from the year, so they never change between releases of the same year:
# UpgradeCode is what makes a newer MSI replace an older one (MajorUpgrade).
set -euo pipefail

year="${1:?year, e.g. 2025}"; version="${2:?version, e.g. 1.1.0}"; dll="${3:?path to VdcNavisLab.dll}"; out="${4:-dist}"
[ -f "$dll" ] || { echo "no existe el DLL: $dll" >&2; exit 2; }
command -v wixl >/dev/null || { echo "falta wixl (apt install wixl msitools)" >&2; exit 2; }

here="$(cd "$(dirname "$0")" && pwd)"
ns="6ba7b811-9dad-11d1-80b4-00c04fd430c8"   # uuid namespace URL
guid() { python3 -c "import uuid,sys; print(str(uuid.uuid5(uuid.UUID('$ns'), sys.argv[1])).upper())" "$1"; }
upgrade="$(guid "https://vdcprocesslab.com/vdc-navis-lab/addin/upgrade/$year")"
component="$(guid "https://vdcprocesslab.com/vdc-navis-lab/addin/component/$year")"

mkdir -p "$out"
msi="$out/VdcNavisLab-$year-$version.msi"
wixl -a x64 -v \
  -D Year="$year" -D Version="$version" -D UpgradeCode="$upgrade" -D ComponentGuid="$component" -D Dll="$dll" \
  -o "$msi" "$here/msi/VdcNavisLab.wxs"

# Check what was built: the payload goes where Navisworks looks for plugins, and it is byte for byte the DLL given.
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
msiextract -C "$tmp" "$msi" >/dev/null
want="Autodesk/Navisworks Manage $year/Plugins/VdcNavisLab/VdcNavisLab.dll"
[ -f "$tmp/$want" ] || { echo "FALLA: el MSI no deja $want" >&2; exit 1; }
a="$(sha256sum "$dll" | cut -d' ' -f1)"; b="$(sha256sum "$tmp/$want" | cut -d' ' -f1)"
[ "$a" = "$b" ] || { echo "FALLA: el DLL dentro del MSI no coincide con el origen" >&2; exit 1; }
echo "OK  $msi  ($(stat -c %s "$msi") bytes)  year=$year version=$version"
echo "    UpgradeCode $upgrade"
echo "    sha256 DLL  $a"
