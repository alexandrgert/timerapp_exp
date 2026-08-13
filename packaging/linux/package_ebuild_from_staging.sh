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
