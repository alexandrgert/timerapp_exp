#!/usr/bin/env bash
# packaging/linux/package_ebuild_from_staging.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${VERSION:?VERSION required}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
PACKAGE_NAME="timerapp-exp"
GENTOO_PACKAGE_DIR="$PROJECT_DIR/packaging/linux/gentoo/app-misc/$PACKAGE_NAME"

if [[ ! "$VERSION" =~ ^[0-9]+(\.[0-9]+){2}([._-][[:alnum:]]+)*$ ]]; then
  echo "Invalid VERSION=$VERSION; expected a semantic version such as 1.2.3." >&2
  exit 1
fi

manifest_line() {
  local kind="$1"
  local file="$2"
  local name size sha512 blake2b

  name="$(basename "$file")"
  size="$(stat -c%s "$file")"
  sha512="$(sha512sum "$file" | awk '{print $1}')"

  if command -v b2sum >/dev/null 2>&1; then
    blake2b="$(b2sum "$file" | awk '{print $1}')"
    printf '%s %s %s BLAKE2B %s SHA512 %s\n' "$kind" "$name" "$size" "$blake2b" "$sha512"
  elif blake2b="$(openssl dgst -blake2b512 "$file" 2>/dev/null | awk '{print $NF}')" && [[ -n "$blake2b" ]]; then
    printf '%s %s %s BLAKE2B %s SHA512 %s\n' "$kind" "$name" "$size" "$blake2b" "$sha512"
  else
    printf '%s %s %s SHA512 %s\n' "$kind" "$name" "$size" "$sha512"
  fi
}

distfile="${DIST_DIR}/${PACKAGE_NAME}-${VERSION}-linux-amd64.tar.xz"
if [[ ! -f "$distfile" ]]; then
  echo "Missing distfile: $distfile" >&2
  echo "timerapp-exp-${VERSION}-linux-amd64.tar.xz must exist in DIST_DIR before ebuild packaging so Manifest can include a real DIST checksum." >&2
  exit 1
fi

metadata="$GENTOO_PACKAGE_DIR/metadata.xml"
if [[ ! -f "$metadata" ]]; then
  echo "Missing Gentoo metadata: $metadata" >&2
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

generated_ebuild="$work/generated.ebuild"
cat > "$generated_ebuild" <<'EOF'
EAPI=8

DESCRIPTION="TaskTimer Experiment"
HOMEPAGE="https://github.com/alexandrgert/timerapp_exp"
SRC_URI="https://github.com/alexandrgert/timerapp_exp/releases/download/v${PV}/timerapp-exp-${PV}-linux-amd64.tar.xz"
S="${WORKDIR}"

LICENSE="MIT"
SLOT="0"
KEYWORDS="~amd64"
RESTRICT="strip mirror"

src_install() {
	rm -f INSTALL.txt || die
	[[ -d opt && -d usr ]] || die "Release archive is missing opt/ or usr/"
	cp -a opt usr "${ED}/" || die
}
EOF

overlay="$work/timerapp-exp-overlay"
overlay_package_dir="$overlay/app-misc/$PACKAGE_NAME"
mkdir -p "$overlay_package_dir" "$overlay/profiles" "$overlay/metadata" "$DIST_DIR"
cp "$metadata" "$overlay_package_dir/"
cp "$generated_ebuild" "$overlay_package_dir/${PACKAGE_NAME}-${VERSION}.ebuild"
{
  manifest_line EBUILD "$overlay_package_dir/${PACKAGE_NAME}-${VERSION}.ebuild"
  manifest_line DIST "$distfile"
} > "$overlay_package_dir/Manifest"
printf '%s\n' 'timerapp-exp' > "$overlay/profiles/repo_name"
cat > "$overlay/metadata/layout.conf" <<'EOF'
masters = gentoo
thin-manifests = true
EOF

ebuild_output="$DIST_DIR/${PACKAGE_NAME}-${VERSION}.ebuild"
overlay_output="$DIST_DIR/${PACKAGE_NAME}-${VERSION}-gentoo-overlay.tar.xz"
rm -f "$ebuild_output" "$overlay_output"
cp "$generated_ebuild" "$ebuild_output"
tar -C "$work" -cJf "$overlay_output" timerapp-exp-overlay

echo "Готово: $ebuild_output"
echo "Готово: $overlay_output"
ls -lh "$ebuild_output" "$overlay_output"
