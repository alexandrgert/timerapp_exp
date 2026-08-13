# Linux Full Package Matrix (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From the existing PyInstaller onedir + staging tree, add Flatpak, Snap, Gentoo ebuild/overlay, PiSi, PET, PUP, and Slax LZM artifacts named `timerapp-exp-*` in the same CI Linux job.

**Architecture:** Approach A — reuse `stage_from_pyinstaller.sh` / `dist/TaskTimer`. Add one packaging script per format under `packaging/linux/`. Extend `build_linux_extra.sh` to call them after rpm/tar/AppImage. Extend CI tooling install + `linux-packages` artifact globs. Fail the job if any required format is missing.

**Tech Stack:** bash, flatpak + flatpak-builder (Freedesktop 24.08), snapcraft (core22, dump plugin, strict), mksquashfs, zip/tar, GitHub Actions ubuntu-latest.

**Spec:** [docs/superpowers/specs/2026-08-13-linux-full-matrix-design.md](../specs/2026-08-13-linux-full-matrix-design.md)

## Global Constraints

- Artifact prefix: `timerapp-exp-` only.
- Flatpak ID: `com.timerapp.exp`; Snap name: `timerapp-exp`.
- Install prefix: `/opt/timerapp_exp`; launcher: `timerapp-exp`.
- Architecture: amd64 / x86_64 only.
- Local `./build_deb.sh`: still **deb only**; do not require flatpak/snapcraft locally.
- CI: `ALLOW_NO_BUMP=1 NO_BUMP=1`; version from `pyproject.toml`.
- ebuild / pisi / pet / pup / lzm: mark **experimental** in docs; still produce valid structure.
- Do not silently skip failed packagers — exit non-zero.
- Repo scope: `timerapp_exp` only.

## File Structure

| Path | Responsibility |
|------|----------------|
| `packaging/linux/package_flatpak_from_onedir.sh` | flatpak build-init → install onedir → bundle |
| `packaging/linux/flatpak/com.timerapp.exp.desktop` | Desktop for Flatpak (Exec=`com.timerapp.exp`) |
| `packaging/linux/package_snap_from_onedir.sh` | generate snapcraft.yaml + snapcraft pack → rename |
| `packaging/linux/package_ebuild_from_staging.sh` | ebuild + overlay tar.xz |
| `packaging/linux/gentoo/app-misc/timerapp-exp/metadata.xml` | Gentoo metadata template |
| `packaging/linux/package_pisi_from_staging.sh` | experimental `.pisi` zip structure |
| `packaging/linux/package_pet_from_staging.sh` | `.pet` + `.pup` |
| `packaging/linux/package_lzm_from_staging.sh` | squashfs `.lzm` |
| `build_linux_extra.sh` | call phase-2 scripts after phase-1 |
| `.github/workflows/ci.yml` | install tools; expand artifact paths |
| Docs + agent rule | full matrix + experimental notes |

**Shared env contract (all packagers):** `VERSION`, `DIST_DIR` (default `dist/`), `PACKAGE_NAME` (default `timerapp-exp`). Staging packagers also need `STAGING_DIR`. Onedir packagers need `ONEDIR` (default `dist/TaskTimer`).

---

### Task 1: Flatpak packager

**Files:**
- Create: `packaging/linux/package_flatpak_from_onedir.sh`
- Create: `packaging/linux/flatpak/com.timerapp.exp.desktop`
- Create: `packaging/linux/flatpak/com.timerapp.exp.metainfo.xml`

**Interfaces:**
- Consumes: `ONEDIR`, `VERSION`, `DIST_DIR`; icon `packaging/linux/tasktimer.svg`
- Produces: `dist/timerapp-exp-<ver>-x86_64.flatpak`
- Runtime: `org.freedesktop.Platform//24.08` + matching Sdk

- [ ] **Step 1: Write desktop + metainfo**

`packaging/linux/flatpak/com.timerapp.exp.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=TaskTimer Experiment
Comment=Experimental desktop task timer with Bitrix24 integration
Exec=com.timerapp.exp
Icon=com.timerapp.exp
Terminal=false
Categories=Office;Utility;
StartupWMClass=timerapp-exp
```

`packaging/linux/flatpak/com.timerapp.exp.metainfo.xml` — AppStream with `id` `com.timerapp.exp`, name TaskTimer Experiment, summary, and `developer` id `timerapp`.

- [ ] **Step 2: Write `package_flatpak_from_onedir.sh`**

```bash
#!/usr/bin/env bash
# packaging/linux/package_flatpak_from_onedir.sh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
VERSION="${VERSION:?VERSION required}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
APP_ID="com.timerapp.exp"
RUNTIME_BRANCH="24.08"
FLATPAK_DIR="$PROJECT_DIR/packaging/linux/flatpak"
OUT="${DIST_DIR}/timerapp-exp-${VERSION}-x86_64.flatpak"

[[ -x "$ONEDIR/TaskTimer" ]] || { echo "Missing onedir" >&2; exit 1; }
command -v flatpak >/dev/null
command -v flatpak-builder >/dev/null || true  # may use build-init path only

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
builddir="$work/build"
repo="$work/repo"

flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true
flatpak install -y --user flathub "org.freedesktop.Platform/${RUNTIME_BRANCH}" "org.freedesktop.Sdk/${RUNTIME_BRANCH}"

flatpak build-init "$builddir" "$APP_ID" org.freedesktop.Sdk org.freedesktop.Platform "$RUNTIME_BRANCH"

# Install binary tree under /app
flatpak build "$builddir" mkdir -p /app/lib/timerapp-exp /app/bin /app/share/applications \
  /app/share/icons/hicolor/scalable/apps /app/share/metainfo
flatpak build "$builddir" cp -a "$ONEDIR/." /app/lib/timerapp-exp/
flatpak build "$builddir" bash -c 'printf "%s\n" "#!/bin/sh" "exec /app/lib/timerapp-exp/TaskTimer \"\$@\"" > /app/bin/com.timerapp.exp && chmod 755 /app/bin/com.timerapp.exp'
flatpak build "$builddir" cp "$FLATPAK_DIR/com.timerapp.exp.desktop" /app/share/applications/
flatpak build "$builddir" cp "$FLATPAK_DIR/com.timerapp.exp.metainfo.xml" /app/share/metainfo/
flatpak build "$builddir" cp "$PROJECT_DIR/packaging/linux/tasktimer.svg" \
  /app/share/icons/hicolor/scalable/apps/com.timerapp.exp.svg

flatpak build-finish "$builddir" \
  --command=com.timerapp.exp \
  --share=network \
  --socket=x11 --socket=wayland --socket=fallback-x11 \
  --socket=session-bus \
  --device=dri \
  --filesystem=home

mkdir -p "$repo"
flatpak build-export "$repo" "$builddir"
mkdir -p "$DIST_DIR"
flatpak build-bundle "$repo" "$OUT" "$APP_ID" --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo

echo "Готово: $OUT"
ls -lh "$OUT"
file "$OUT"
```

- [ ] **Step 3: chmod +x; smoke when tools + onedir exist**

```bash
chmod +x packaging/linux/package_flatpak_from_onedir.sh
# CI will exercise; locally optional:
# VERSION=0.10.0 ONEDIR=dist/TaskTimer ./packaging/linux/package_flatpak_from_onedir.sh
```

- [ ] **Step 4: Commit**

```bash
git add packaging/linux/package_flatpak_from_onedir.sh packaging/linux/flatpak/
git commit -m "feat(linux): add Flatpak packager for com.timerapp.exp"
```

---

### Task 2: Snap packager

**Files:**
- Create: `packaging/linux/package_snap_from_onedir.sh`

**Interfaces:**
- Consumes: `ONEDIR`, `VERSION`, `DIST_DIR`
- Produces: `dist/timerapp-exp-<ver>-amd64.snap` (normalized name)
- Confinement: **strict** + plugs (classic avoided for CI without store)

- [ ] **Step 1: Write packager**

```bash
#!/usr/bin/env bash
# packaging/linux/package_snap_from_onedir.sh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
VERSION="${VERSION:?VERSION required}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
OUT="${DIST_DIR}/timerapp-exp-${VERSION}-amd64.snap"

[[ -x "$ONEDIR/TaskTimer" ]] || { echo "Missing onedir" >&2; exit 1; }
command -v snapcraft >/dev/null

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/prime-src/bin" "$work/prime-src/lib/timerapp-exp"
cp -a "$ONEDIR/." "$work/prime-src/lib/timerapp-exp/"
cat > "$work/prime-src/bin/timerapp-exp" <<'EOF'
#!/bin/sh
exec "$SNAP/lib/timerapp-exp/TaskTimer" "$@"
EOF
chmod 755 "$work/prime-src/bin/timerapp-exp"
cp "$PROJECT_DIR/packaging/linux/tasktimer.svg" "$work/prime-src/timerapp-exp.svg"
cp "$PROJECT_DIR/packaging/linux/timerapp-exp.desktop" "$work/prime-src/timerapp-exp.desktop"
# Fix Exec/Icon paths for snap desktop if needed in YAML

cat > "$work/snapcraft.yaml" <<EOF
name: timerapp-exp
base: core22
version: '${VERSION}'
summary: TaskTimer Experiment
description: |
  Experimental desktop task timer with Bitrix24 integration.
grade: devel
confinement: strict

apps:
  timerapp-exp:
    command: bin/timerapp-exp
    plugs: [network, desktop, desktop-legacy, wayland, x11, opengl, home, gsettings]
    desktop: timerapp-exp.desktop
    common-id: com.timerapp.exp

parts:
  app:
    plugin: dump
    source: ./prime-src
    stage-packages: []
EOF

# Adjust desktop Exec inside prime-src
sed -i 's|^Exec=.*|Exec=timerapp-exp|' "$work/prime-src/timerapp-exp.desktop"
sed -i 's|^Icon=.*|Icon=\${SNAP}/timerapp-exp.svg|' "$work/prime-src/timerapp-exp.desktop" || \
  sed -i 's|^Icon=.*|Icon=timerapp-exp|' "$work/prime-src/timerapp-exp.desktop"

(
  cd "$work"
  snapcraft pack --destructive-mode -o "$OUT" || snapcraft pack --destructive-mode
)
# If snapcraft wrote default name, normalize:
if [[ ! -f "$OUT" ]]; then
  built="$(find "$work" -maxdepth 2 -name 'timerapp-exp_*.snap' | head -n1)"
  [[ -n "$built" ]] || { echo "snapcraft produced no .snap" >&2; exit 1; }
  mkdir -p "$DIST_DIR"
  cp -f "$built" "$OUT"
fi

echo "Готово: $OUT"
ls -lh "$OUT"
unsquashfs -l "$OUT" | head -n 40
```

- [ ] **Step 2: chmod +x**

```bash
chmod +x packaging/linux/package_snap_from_onedir.sh
```

- [ ] **Step 3: Commit**

```bash
git add packaging/linux/package_snap_from_onedir.sh
git commit -m "feat(linux): add Snap packager (strict, dump plugin)"
```

---

### Task 3: Gentoo ebuild + overlay

**Files:**
- Create: `packaging/linux/gentoo/app-misc/timerapp-exp/metadata.xml`
- Create: `packaging/linux/package_ebuild_from_staging.sh`

**Interfaces:**
- Consumes: `VERSION`, `DIST_DIR` (staging optional — ebuild references published tar.xz name)
- Produces:
  - `dist/timerapp-exp-<ver>.ebuild`
  - `dist/timerapp-exp-<ver>-gentoo-overlay.tar.xz`

- [ ] **Step 1: metadata.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "https://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
  <maintainer type="person">
    <email>noreply@example.com</email>
    <name>TaskTimer Experiment</name>
  </maintainer>
  <upstream>
    <remote-id type="github">alexandrgert/timerapp_exp</remote-id>
  </upstream>
</pkgmetadata>
```

- [ ] **Step 2: package_ebuild_from_staging.sh**

Generate ebuild that installs binary tree from `timerapp-exp-${PV}-linux-amd64.tar.xz` (SRC_URI placeholder pointing at GitHub release URL pattern), `KEYWORDS="~amd64"`, `RESTRICT="strip"`, `src_install` copies `opt/` and `usr/` from the tarball (exclude INSTALL.txt).

```bash
# Outline of generated ebuild body:
# EAPI=8
# DESCRIPTION="TaskTimer Experiment"
# HOMEPAGE="https://github.com/alexandrgert/timerapp_exp"
# SRC_URI="https://github.com/alexandrgert/timerapp_exp/releases/download/v${PV}/timerapp-exp-${PV}-linux-amd64.tar.xz"
# S="${WORKDIR}"
# LICENSE="MIT"
# SLOT="0"
# KEYWORDS="~amd64"
# RESTRICT="strip mirror"
# src_install() {
#   rm -f INSTALL.txt || true
#   insinto /
#   doins -r opt
#   exeinto /usr/bin
#   doexe usr/bin/timerapp-exp
#   ...
# }
```

Pack overlay:

```bash
overlay="$work/timerapp-exp-overlay"
mkdir -p "$overlay/app-misc/timerapp-exp"
cp metadata.xml "$overlay/app-misc/timerapp-exp/"
cp generated.ebuild "$overlay/app-misc/timerapp-exp/timerapp-exp-${VERSION}.ebuild"
# optional: profiles/repo_name = timerapp-exp
mkdir -p "$overlay/profiles"
echo "timerapp-exp" > "$overlay/profiles/repo_name"
mkdir -p "$overlay/metadata"
cat > "$overlay/metadata/layout.conf" <<'EOF'
masters = gentoo
thin-manifests = true
EOF
tar -C "$work" -cJf "${DIST_DIR}/timerapp-exp-${VERSION}-gentoo-overlay.tar.xz" timerapp-exp-overlay
cp generated.ebuild "${DIST_DIR}/timerapp-exp-${VERSION}.ebuild"
```

Smoke: `grep -q EAPI "$DIST_DIR/timerapp-exp-${VERSION}.ebuild"` and tar contains `app-misc/timerapp-exp/`.

- [ ] **Step 3: chmod +x; commit**

```bash
chmod +x packaging/linux/package_ebuild_from_staging.sh
git add packaging/linux/gentoo packaging/linux/package_ebuild_from_staging.sh
git commit -m "feat(linux): add experimental Gentoo ebuild and overlay artifact"
```

---

### Task 4: PiSi packager (experimental)

**Files:**
- Create: `packaging/linux/package_pisi_from_staging.sh`

**Interfaces:**
- Consumes: `STAGING_DIR`, `VERSION`, `DIST_DIR`
- Produces: `dist/timerapp-exp-<ver>-x86_64.pisi`

- [ ] **Step 1: Implement `.pisi` as zip** containing:
  - `metadata.xml` (Package Name, Version, Summary, Description, Distribution, Architecture x86_64)
  - `files.xml` (Path list of installed files with type)
  - `install.tar.xz` — tarball of staging tree (`opt/`, `usr/`)

```bash
#!/usr/bin/env bash
set -euo pipefail
# ... resolve STAGING_DIR VERSION DIST_DIR
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
mkdir -p "$work/pisi"
tar -C "$STAGING_DIR" -cJf "$work/pisi/install.tar.xz" .
# write metadata.xml + files.xml (enumerate via find)
(
  cd "$work/pisi"
  zip -q "${DIST_DIR}/timerapp-exp-${VERSION}-x86_64.pisi" metadata.xml files.xml install.tar.xz
)
# verify: unzip -l ... | grep -E 'metadata.xml|install.tar.xz'
```

- [ ] **Step 2: chmod +x; commit**

```bash
chmod +x packaging/linux/package_pisi_from_staging.sh
git add packaging/linux/package_pisi_from_staging.sh
git commit -m "feat(linux): add experimental PiSi packager from staging"
```

---

### Task 5: PET + PUP packagers (experimental)

**Files:**
- Create: `packaging/linux/package_pet_from_staging.sh`

**Interfaces:**
- Consumes: `STAGING_DIR`, `VERSION`, `DIST_DIR`
- Produces: `dist/timerapp-exp-<ver>-amd64.pet`, `dist/timerapp-exp-<ver>-amd64.pup`

- [ ] **Step 1: PET**

Classic PET: directory named `timerapp-exp-<ver>-amd64` containing staging files + `pet.specs`:

```
timerapp-exp|VERSION||Official|1024K||timerapp-exp-<ver>-amd64.pet||TaskTimer Experiment||||
```

Then:

```bash
rootname="timerapp-exp-${VERSION}-amd64"
mkdir -p "$work/$rootname"
cp -a "$STAGING_DIR/." "$work/$rootname/"
echo "timerapp-exp|${VERSION}||Official|1024K||${rootname}.pet||TaskTimer Experiment||||" \
  > "$work/$rootname/pet.specs"
tar -C "$work" -czf "${DIST_DIR}/${rootname}.pet" "$rootname"
```

- [ ] **Step 2: PUP**

Produce `.pup` as gzip-compressed tar of the same tree (Puppy companion package), same rootname with `.pup` extension. Document both as experimental.

```bash
tar -C "$work" -czf "${DIST_DIR}/${rootname}.pup" "$rootname"
# smoke: tar -tzf ... | grep 'usr/bin/timerapp-exp'
```

- [ ] **Step 3: chmod +x; commit**

```bash
chmod +x packaging/linux/package_pet_from_staging.sh
git add packaging/linux/package_pet_from_staging.sh
git commit -m "feat(linux): add experimental PET and PUP packagers"
```

---

### Task 6: Slax LZM packager (experimental)

**Files:**
- Create: `packaging/linux/package_lzm_from_staging.sh`

**Interfaces:**
- Consumes: `STAGING_DIR`, `VERSION`, `DIST_DIR`
- Produces: `dist/timerapp-exp-<ver>-amd64.lzm`

- [ ] **Step 1: mksquashfs**

```bash
#!/usr/bin/env bash
set -euo pipefail
# ...
OUT="${DIST_DIR}/timerapp-exp-${VERSION}-amd64.lzm"
command -v mksquashfs >/dev/null
mksquashfs "$STAGING_DIR" "$OUT" -comp xz -noappend
file "$OUT"
# optional: unsquashfs -l "$OUT" | grep timerapp-exp
```

- [ ] **Step 2: chmod +x; commit**

```bash
chmod +x packaging/linux/package_lzm_from_staging.sh
git add packaging/linux/package_lzm_from_staging.sh
git commit -m "feat(linux): add experimental Slax LZM packager"
```

---

### Task 7: Wire `build_linux_extra.sh` + CI

**Files:**
- Modify: `build_linux_extra.sh`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- After phase-1 packagers, call flatpak, snap, ebuild, pisi, pet, lzm with same `VERSION`/`STAGING_DIR`/`ONEDIR`/`DIST_DIR` exports.
- Staging must **not** be deleted before niche packagers finish (keep trap at end only).

- [ ] **Step 1: Extend `build_linux_extra.sh`**

```bash
# after package_appimage_from_onedir.sh:
"$PACKAGING_DIR/package_flatpak_from_onedir.sh"
"$PACKAGING_DIR/package_snap_from_onedir.sh"
"$PACKAGING_DIR/package_ebuild_from_staging.sh"
"$PACKAGING_DIR/package_pisi_from_staging.sh"
"$PACKAGING_DIR/package_pet_from_staging.sh"
"$PACKAGING_DIR/package_lzm_from_staging.sh"
```

- [ ] **Step 2: CI — install tools** (extend existing “Install Linux extra packaging tools” step)

```bash
sudo apt-get install -y --no-install-recommends \
  flatpak flatpak-builder ostree squashfs-tools zip unzip \
  snapd
# snapcraft:
sudo snap install snapcraft --classic   # if snapd usable on GHA
# OR: pip/apt alternative documented — prefer:
sudo snap install snapcraft --classic
# Ensure flathub remote available for the packager script
```

If `snap install snapcraft` fails on runner, install via:

```bash
curl -fL -o /tmp/snapcraft.snap https://api.snapcraft.io/api/v1/snaps/download/... 
# Prefer documented GHA pattern: `sudo snap install snapcraft --classic` after ensuring snapd service.
# Fallback used in many projects: pipx install snapcraft — pin a known version if needed.
```

Also install `file`. Keep fpm + appimagetool as today.

- [ ] **Step 3: Expand artifact upload paths**

```yaml
path: |
  dist/timerapp-exp-*-amd64.deb
  dist/timerapp-exp-*-amd64.rpm
  dist/timerapp-exp-*-linux-amd64.tar.xz
  dist/timerapp-exp-*-linux-amd64.tgz
  dist/timerapp-exp-*-x86_64.AppImage
  dist/timerapp-exp-*-x86_64.flatpak
  dist/timerapp-exp-*-amd64.snap
  dist/timerapp-exp-*.ebuild
  dist/timerapp-exp-*-gentoo-overlay.tar.xz
  dist/timerapp-exp-*-x86_64.pisi
  dist/timerapp-exp-*-amd64.pet
  dist/timerapp-exp-*-amd64.pup
  dist/timerapp-exp-*-amd64.lzm
if-no-files-found: error
```

- [ ] **Step 4: Commit**

```bash
git add build_linux_extra.sh .github/workflows/ci.yml
git commit -m "ci(linux): build full package matrix in linux-packages artifact"
```

---

### Task 8: Documentation + agent rule

**Files:**
- Modify: `README.md` (Linux downloads / formats section)
- Modify: `ИНСТРУКЦИЯ.md`
- Modify: `docs/system-requirements.md` (if present)
- Modify: `docs/architecture-cross-platform.md`
- Modify: `.cursor/rules/` agent packaging note if it lists only five formats
- Modify: `docs/superpowers/specs/2026-08-13-linux-full-matrix-design.md` — set status to **approved**

- [ ] **Step 1: Docs updates**

Document full matrix; Flatpak ID `com.timerapp.exp`; Snap `timerapp-exp` (strict); experimental badge for ebuild/pisi/pet/pup/lzm; local = deb only.

- [ ] **Step 2: Commit**

```bash
git add README.md ИНСТРУКЦИЯ.md docs/ .cursor/rules/
git commit -m "docs: document full Linux package matrix for Experiment"
```

---

### Task 9: CI verification gate

**Files:** none (run on PR)

- [ ] **Step 1: Push branch / ensure PR #1 updated**

- [ ] **Step 2: Wait for `build-deb` green**

- [ ] **Step 3: Download `linux-packages` artifact; verify all expected filenames for `PACKAGE_VERSION` exist and are non-empty**

```bash
ls -lh timerapp-exp-*
# expect: deb rpm tar.xz tgz AppImage flatpak snap ebuild overlay pisi pet pup lzm
```

- [ ] **Step 4: Spot-check**

```bash
file *.flatpak *.snap *.lzm *.pet *.pisi
tar -tJf *-gentoo-overlay.tar.xz | head
unsquashfs -l *.snap | head
```

If Flatpak/Snap fail in CI: fix tooling in a follow-up commit on the same branch (do not merge until green).

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Flatpak `com.timerapp.exp` bundle | 1, 7 |
| Snap normalized `timerapp-exp-<ver>-amd64.snap` | 2, 7 |
| ebuild + overlay | 3, 7 |
| pisi | 4, 7 |
| pet + pup | 5, 7 |
| lzm | 6, 7 |
| One CI job, Approach A | 7 |
| Docs + experimental marks | 8 |
| Acceptance / CI green | 9 |
| Local deb-only preserved | 7 (no change to `build_deb.sh` extras) |

## Self-review notes

- No TBD placeholders in packager contracts.
- Snap Icon=`${SNAP}/...` may need YAML escaping — implementer must ensure desktop file is valid for snapcraft.
- Flatpak `flatpak build cp -a` may need `bash -c` with paths mounted; if `flatpak build` cannot see host `ONEDIR`, copy into `$work` first then `flatpak build ... cp -a /run/build/...` or use `flatpak-builder` with `type: dir` module pointing at copied onedir — adjust Task 1 script during implementation if host path visibility fails.
- Staging trap in `build_linux_extra.sh` must remain until **all** staging-based packagers complete.
