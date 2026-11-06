#!/usr/bin/env bash
# Assembles the field-test folder to copy to another machine.
#   installer/build-field-kit.sh --msi-dir <dir with VdcNavisLab-<year>-<version>.msi> --mcpb <...-pro-offline-windows.mcpb> --token <license.token> --out <folder>
# The folder holds a license token, so it is refused unless it is outside git or git-ignored (dist/ is). Nothing of Autodesk goes in it
# beyond the add-in DLLs that the MSIs already contain (our own code).
set -euo pipefail
msi_dir=""; mcpb=""; token=""; out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --msi-dir) msi_dir="$2"; shift 2;;
    --mcpb) mcpb="$2"; shift 2;;
    --token) token="$2"; shift 2;;
    --out) out="$2"; shift 2;;
    *) echo "argumento desconocido: $1" >&2; exit 2;;
  esac
done
[ -d "$msi_dir" ] && [ -f "$mcpb" ] && [ -f "$token" ] && [ -n "$out" ] || { echo "uso: build-field-kit.sh --msi-dir D --mcpb F --token F --out D" >&2; exit 2; }
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$out"; out="$(cd "$out" && pwd)"
if git -C "$out" rev-parse --show-toplevel >/dev/null 2>&1 && ! git -C "$out" check-ignore -q "$out"; then
  echo "FALLA: $out esta dentro de un repositorio git y no esta ignorado; la carpeta lleva una licencia." >&2; exit 1
fi
ver="$(basename "$mcpb" | sed -E 's/^vdc-navis-lab-([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"
shopt -s nullglob
msis=("$msi_dir"/VdcNavisLab-*-"$ver".msi)
[ ${#msis[@]} -gt 0 ] || { echo "FALLA: no hay MSI $ver en $msi_dir" >&2; exit 1; }
rm -rf "$out/msi" "$out/licencia" "$out/resultados"; mkdir -p "$out/msi" "$out/licencia" "$out/resultados"
cp "${msis[@]}" "$out/msi/"; cp "$mcpb" "$out/"; cp "$token" "$out/licencia/license.token"
cp "$here/campo/campo.ps1" "$here/campo/instalar-prueba.ps1" "$here/campo/desinstalar-prueba.ps1" "$out/"
years=""; for m in "${msis[@]}"; do y="$(basename "$m" | cut -d- -f2)"; years="${years:+$years, }$y"; done
years="$(echo "$years" | sed -E 's/, ([0-9]{4})$/ y \1/')"
sed -e "s/@VERSION@/$ver/g" -e "s/@YEARS@/$years/g" "$here/campo/INSTRUCCIONES.html" > "$out/INSTRUCCIONES.html"
( cd "$out" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt )
echo "OK  $out  (version $ver, Navisworks $years)"
