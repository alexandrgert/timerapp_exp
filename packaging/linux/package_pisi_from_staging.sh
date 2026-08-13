#!/usr/bin/env bash
# packaging/linux/package_pisi_from_staging.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="${STAGING_DIR:?STAGING_DIR required}"
VERSION="${VERSION:?VERSION required}"
PACKAGE_NAME="${PACKAGE_NAME:-timerapp-exp}"
PACKAGE_RELEASE="${PACKAGE_RELEASE:-1}"
MAINTAINER="${MAINTAINER:-alexandrgert <alexandrgert@gmail.com>}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
PACKAGE_TITLE="${PACKAGE_TITLE:-TaskTimer Experiment}"
PISI_DISTRIBUTION="${PISI_DISTRIBUTION:-timerapp-exp}"
PISI_DISTRIBUTION_RELEASE="${PISI_DISTRIBUTION_RELEASE:-experimental}"
PISI_ARCH="${PISI_ARCH:-x86_64}"

if [[ ! -d "$STAGING_DIR" ]]; then
  echo "Missing staging directory: $STAGING_DIR" >&2
  exit 1
fi
STAGING_DIR="$(cd "$STAGING_DIR" && pwd)"

for required_path in opt usr; do
  if [[ ! -e "$STAGING_DIR/$required_path" ]]; then
    echo "Missing staging path: $STAGING_DIR/$required_path" >&2
    exit 1
  fi
done

for tool in tar zip unzip find sha1sum; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 1
  fi
done

packager_name="${MAINTAINER%% *}"
packager_email="${MAINTAINER#*<}"
packager_email="${packager_email%>}"

xml_escape() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  value="${value//\"/&quot;}"
  printf '%s' "$value"
}

file_type_for() {
  local path="$1"
  if [[ -L "$path" ]]; then
    printf 'symlink'
  elif [[ -d "$path" ]]; then
    printf 'directory'
  elif [[ -x "$path" ]]; then
    printf 'executable'
  else
    printf 'data'
  fi
}

installed_size_kb="$(
  du -sk "$STAGING_DIR" 2>/dev/null | awk '{print $1}'
)"
installed_size_bytes=$((installed_size_kb * 1024))
build_date="$(date -u +%Y-%m-%d)"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
pisi_dir="$work/pisi"
mkdir -p "$pisi_dir"

tar -C "$STAGING_DIR" -cJf "$pisi_dir/install.tar.xz" .

files_xml="$pisi_dir/files.xml"
{
  printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>'
  printf '%s\n' '<Files>'
  while IFS= read -r -d '' rel_path; do
    abs_path="$STAGING_DIR/$rel_path"
    ftype="$(file_type_for "$abs_path")"
    fsize="$(stat -c '%s' "$abs_path")"
    fuid="$(stat -c '%u' "$abs_path")"
    fgid="$(stat -c '%g' "$abs_path")"
    fmode="$(stat -c '%a' "$abs_path")"
    printf '%s\n' '  <File>'
    printf '    <Path>%s</Path>\n' "$(xml_escape "$rel_path")"
    printf '    <Type>%s</Type>\n' "$ftype"
    printf '    <Size>%s</Size>\n' "$fsize"
    printf '    <Uid>%s</Uid>\n' "$fuid"
    printf '    <Gid>%s</Gid>\n' "$fgid"
    printf '    <Mode>0o%s</Mode>\n' "$fmode"
    if [[ -f "$abs_path" && ! -L "$abs_path" ]]; then
      fhash="$(sha1sum "$abs_path" | awk '{print $1}')"
      printf '    <Hash>%s</Hash>\n' "$fhash"
    elif [[ -L "$abs_path" ]]; then
      link_target="$(readlink -n "$abs_path")"
      fhash="$(printf '%s' "$link_target" | sha1sum | awk '{print $1}')"
      printf '    <Hash>%s</Hash>\n' "$fhash"
    fi
    printf '%s\n' '  </File>'
  done < <(find "$STAGING_DIR" -mindepth 1 -printf '%P\0' | sort -z)
  printf '%s\n' '</Files>'
} > "$files_xml"

metadata_xml="$pisi_dir/metadata.xml"
cat > "$metadata_xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<PISI>
  <Source>
    <Name>$(xml_escape "$PACKAGE_NAME")</Name>
    <Homepage>https://github.com/alexandrgert/timerapp_exp</Homepage>
    <Packager>
      <Name>$(xml_escape "$packager_name")</Name>
      <Email>$(xml_escape "$packager_email")</Email>
    </Packager>
  </Source>
  <Package>
    <Name>$(xml_escape "$PACKAGE_NAME")</Name>
    <Summary>$(xml_escape "$PACKAGE_TITLE")</Summary>
    <Description>Experimental desktop task timer: daily plan, focus mode, Bitrix24 tasks and smart-process projects.</Description>
    <Version>$(xml_escape "$VERSION")</Version>
    <Release>$(xml_escape "$PACKAGE_RELEASE")</Release>
    <License>MIT</License>
    <IsA>app:gui</IsA>
    <PartOf>desktop</PartOf>
    <Distribution>$(xml_escape "$PISI_DISTRIBUTION")</Distribution>
    <DistributionRelease>$(xml_escape "$PISI_DISTRIBUTION_RELEASE")</DistributionRelease>
    <Architecture>$(xml_escape "$PISI_ARCH")</Architecture>
    <InstalledSize>${installed_size_bytes}</InstalledSize>
    <PackageFormat>1.2</PackageFormat>
    <History>
      <Update release="$(xml_escape "$PACKAGE_RELEASE")" type="binary">
        <Date>${build_date}</Date>
        <Version>$(xml_escape "$VERSION")</Version>
        <Name>$(xml_escape "$packager_name")</Name>
        <Email>$(xml_escape "$packager_email")</Email>
      </Update>
    </History>
  </Package>
</PISI>
EOF

mkdir -p "$DIST_DIR"
DIST_DIR="$(cd "$DIST_DIR" && pwd)"
output="${DIST_DIR}/${PACKAGE_NAME}-${VERSION}-${PISI_ARCH}.pisi"
rm -f "$output"
(
  cd "$pisi_dir"
  zip -q "$output" metadata.xml files.xml install.tar.xz
)

listing="$work/unzip-listing.txt"
unzip -l "$output" > "$listing"
for required_member in metadata.xml files.xml install.tar.xz; do
  if ! grep -Fq "$required_member" "$listing"; then
    echo "Missing $required_member in $output" >&2
    exit 1
  fi
done

if ! file "$output" | grep -qi 'zip archive'; then
  echo "Unexpected file type for $output" >&2
  exit 1
fi

echo "Готово: $output"
ls -lh "$output"
