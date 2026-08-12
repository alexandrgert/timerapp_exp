# Linux Extra Packages (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From one PyInstaller onedir, produce CI Linux artifacts `.deb`, `.rpm`, `.tar.xz`, `.tgz`, and `.AppImage` named `timerapp-exp-*`; keep local builds as deb-only.

**Architecture:** Extract shared staging (`opt/` + `usr/bin` launcher + desktop + icon) from `build_deb.sh`. Add `build_linux_extra.sh` for rpm/tar/AppImage from an existing onedir or staging dir. Extend the single CI `build-deb` job to run PyInstaller once, then package all five formats and upload them.

**Tech Stack:** bash, PyInstaller onedir (`TaskTimer-linux.spec`), `dpkg-deb`, `fpm` (dir→rpm), `tar`, `linuxdeploy` + `appimagetool` (pinned downloads in CI), GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-08-12-linux-extra-packages-design.md](../specs/2026-08-12-linux-extra-packages-design.md)

## Global Constraints

- Artifact prefix: `timerapp-exp-` only (not `tasktimer-link-b24-`).
- Install prefix: `/opt/timerapp_exp`; launcher binary name: `timerapp-exp`.
- Architecture: amd64 / x86_64 only.
- Local `./build_deb.sh`: still builds **only** `.deb` (may call shared staging); does **not** require fpm/appimagetool.
- CI: `ALLOW_NO_BUMP=1 NO_BUMP=1`; version from `pyproject.toml`.
- Out of scope: flatpak, snap, ebuild, pisi, pet/pup, lzm.
- Do not use `alien` to convert deb→rpm.

## File Structure

| Path | Responsibility |
|------|----------------|
| `packaging/linux/stage_from_pyinstaller.sh` | Build staging filesystem tree from `dist/TaskTimer` |
| `packaging/linux/package_deb_from_staging.sh` | DEBIAN control + `dpkg-deb` from staging |
| `packaging/linux/package_rpm_from_staging.sh` | `fpm` → rpm |
| `packaging/linux/package_tarballs_from_staging.sh` | `.tar.xz` + `.tgz` + `INSTALL.txt` |
| `packaging/linux/package_appimage_from_onedir.sh` | AppDir + linuxdeploy/appimagetool |
| `build_deb.sh` | Thin: bump/version → PyInstaller → stage → deb |
| `build_linux_extra.sh` | CI helper: stage (if needed) → rpm/tar/AppImage into `dist/` |
| `.github/workflows/ci.yml` | One Linux job: all five artifacts |
| Docs + `.cursor/rules/...` | Matrix and “CI-only extras” rule |

---

### Task 1: Shared staging script

**Files:**
- Create: `packaging/linux/stage_from_pyinstaller.sh`
- Test: manual shell check (no pytest for bash staging)

**Interfaces:**
- Produces: executable script; env/args:
  - `ONEDIR` (default `dist/TaskTimer`)
  - `STAGING_DIR` (required output directory, empty or created)
  - `VERSION`, `INSTALL_PREFIX` (default `/opt/timerapp_exp`), `BIN_NAME` (default `timerapp-exp`), `PACKAGE_TITLE` (default `TaskTimer Experiment`), `PACKAGING_DIR` (default `packaging/linux`)
- Layout under `$STAGING_DIR`:
  - `$INSTALL_PREFIX#/` copy of onedir + `VERSION` file
  - `usr/bin/$BIN_NAME` wrapper `exec $INSTALL_PREFIX/TaskTimer "$@"`
  - `usr/share/applications/timerapp-exp.desktop`
  - `usr/share/icons/hicolor/scalable/apps/timerapp-exp.svg`

- [ ] **Step 1: Create staging script**

```bash
#!/usr/bin/env bash
# packaging/linux/stage_from_pyinstaller.sh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
STAGING_DIR="${STAGING_DIR:?STAGING_DIR required}"
VERSION="${VERSION:?VERSION required}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/timerapp_exp}"
BIN_NAME="${BIN_NAME:-timerapp-exp}"
PACKAGE_TITLE="${PACKAGE_TITLE:-TaskTimer Experiment}"
PACKAGING_DIR="${PACKAGING_DIR:-$PROJECT_DIR/packaging/linux}"

if [[ ! -x "$ONEDIR/TaskTimer" ]]; then
  echo "Missing onedir binary: $ONEDIR/TaskTimer" >&2
  exit 1
fi

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
opt_rel="${INSTALL_PREFIX#/}"
install_dir="$STAGING_DIR/$opt_rel"
mkdir -p "$install_dir"
cp -a "$ONEDIR/." "$install_dir/"
echo "$VERSION" > "$install_dir/VERSION"

mkdir -p "$STAGING_DIR/usr/bin"
cat > "$STAGING_DIR/usr/bin/$BIN_NAME" <<EOF
#!/bin/sh
exec ${INSTALL_PREFIX}/TaskTimer "\$@"
EOF
chmod 755 "$STAGING_DIR/usr/bin/$BIN_NAME"

mkdir -p "$STAGING_DIR/usr/share/applications"
cat > "$STAGING_DIR/usr/share/applications/timerapp-exp.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${PACKAGE_TITLE}
Name[ru]=${PACKAGE_TITLE}
Comment=Experimental desktop task timer with Bitrix24 integration
Comment[ru]=Экспериментальный таймер задач с интеграцией Битрикс24
Exec=${BIN_NAME}
Icon=timerapp-exp
Terminal=false
Categories=Office;Utility;
StartupWMClass=timerapp-exp
EOF

mkdir -p "$STAGING_DIR/usr/share/icons/hicolor/scalable/apps"
cp "$PACKAGING_DIR/tasktimer.svg" \
  "$STAGING_DIR/usr/share/icons/hicolor/scalable/apps/timerapp-exp.svg"

echo "Staged into $STAGING_DIR"
```

- [ ] **Step 2: chmod +x**

```bash
chmod +x packaging/linux/stage_from_pyinstaller.sh
```

- [ ] **Step 3: Smoke with existing onedir (if `dist/TaskTimer` exists from prior build)**

```bash
export VERSION=0.0.0-test STAGING_DIR=/tmp/timerapp-stage-test
./packaging/linux/stage_from_pyinstaller.sh
test -x /tmp/timerapp-stage-test/usr/bin/timerapp-exp
test -f /tmp/timerapp-stage-test/opt/timerapp_exp/VERSION
```

Expected: exits 0; files present.

- [ ] **Step 4: Commit**

```bash
git add packaging/linux/stage_from_pyinstaller.sh
git commit -m "build: add shared Linux staging from PyInstaller onedir"
```

---

### Task 2: Deb packaging from staging + refactor `build_deb.sh`

**Files:**
- Create: `packaging/linux/package_deb_from_staging.sh`
- Modify: `build_deb.sh` (replace inline staging/DEBIAN block with calls to scripts)

**Interfaces:**
- Consumes: staging dir from Task 1
- Produces: `dist/timerapp-exp-<ver>-amd64.deb`
- `package_deb_from_staging.sh` args/env: `STAGING_DIR`, `VERSION`, `PACKAGE_NAME`, `TARGET_ARCH`, `MAINTAINER`, `DIST_DIR`, same Depends string as current `build_deb.sh`

- [ ] **Step 1: Move DEBIAN control/preinst/postinst/postrm + `dpkg-deb` into `package_deb_from_staging.sh`**

Copy logic from current `build_deb.sh` lines that create `DEBIAN/` and run `dpkg-deb`, but operate on a **copy** of staging (or add `DEBIAN` into a temp copy of staging) so staging remains reusable for rpm/tar:

```bash
# Sketch — keep Depends / preinst / postinst / postrm text identical to current build_deb.sh
work="$(mktemp -d)"
cp -a "$STAGING_DIR/." "$work/"
# write DEBIAN/* into $work
dpkg-deb --build --root-owner-group "$work" "$DIST_DIR/${PACKAGE_NAME}-${VERSION}-${TARGET_ARCH}.deb"
rm -rf "$work"
```

- [ ] **Step 2: Refactor `build_deb.sh`**

After PyInstaller succeeds:

```bash
STAGING_DIR="$(mktemp -d)"
export STAGING_DIR VERSION INSTALL_PREFIX BIN_NAME PACKAGE_TITLE
"$PACKAGING_DIR/stage_from_pyinstaller.sh"
"$PACKAGING_DIR/package_deb_from_staging.sh"
rm -rf "$STAGING_DIR"
```

Keep bump/version/pip/PyInstaller preamble unchanged.

- [ ] **Step 3: Local smoke**

```bash
ALLOW_NO_BUMP=1 NO_BUMP=1 ./build_deb.sh
dpkg-deb -I dist/timerapp-exp-*-amd64.deb | grep -E 'Package|Version'
```

Expected: Package `timerapp-exp`, Version matches `pyproject.toml`.

- [ ] **Step 4: Commit**

```bash
git add build_deb.sh packaging/linux/package_deb_from_staging.sh
git commit -m "refactor: build deb from shared Linux staging"
```

---

### Task 3: Tarballs from staging

**Files:**
- Create: `packaging/linux/package_tarballs_from_staging.sh`

**Interfaces:**
- Consumes: `STAGING_DIR`, `VERSION`, `DIST_DIR`, `PACKAGE_NAME`
- Produces:
  - `dist/timerapp-exp-<ver>-linux-amd64.tar.xz`
  - `dist/timerapp-exp-<ver>-linux-amd64.tgz`
- Archive root contains `opt/`, `usr/`, and `INSTALL.txt` (not under `/`).

- [ ] **Step 1: Implement tarball script**

```bash
#!/usr/bin/env bash
set -euo pipefail
# write INSTALL.txt into staging copy:
#   Install: sudo tar -C / -xvf timerapp-exp-…-linux-amd64.tar.xz --exclude=INSTALL.txt
#   or extract then sudo cp -a opt usr /
#   Remove: sudo rm -rf /opt/timerapp_exp /usr/bin/timerapp-exp …
work="$(mktemp -d)"
cp -a "$STAGING_DIR/." "$work/"
cat > "$work/INSTALL.txt" <<'EOF'
TaskTimer Experiment — portable tree
Install (as root): tar -C / -xvf THIS_ARCHIVE --exclude=INSTALL.txt
Remove: rm -rf /opt/timerapp_exp /usr/bin/timerapp-exp \
  /usr/share/applications/timerapp-exp.desktop \
  /usr/share/icons/hicolor/scalable/apps/timerapp-exp.svg
EOF
base="${PACKAGE_NAME}-${VERSION}-linux-amd64"
tar -C "$work" -cJf "${DIST_DIR}/${base}.tar.xz" .
tar -C "$work" -czf "${DIST_DIR}/${base}.tgz" .
rm -rf "$work"
```

- [ ] **Step 2: Smoke**

```bash
# after staging exists
export STAGING_DIR=... VERSION=... DIST_DIR=dist PACKAGE_NAME=timerapp-exp
./packaging/linux/package_tarballs_from_staging.sh
tar -tJf dist/timerapp-exp-*-linux-amd64.tar.xz | grep 'usr/bin/timerapp-exp'
tar -tzf dist/timerapp-exp-*-linux-amd64.tgz | grep 'opt/timerapp_exp/TaskTimer'
```

Expected: both archives list launcher and binary.

- [ ] **Step 3: Commit**

```bash
git add packaging/linux/package_tarballs_from_staging.sh
git commit -m "build: add linux tar.xz and tgz from staging"
```

---

### Task 4: RPM from staging via fpm

**Files:**
- Create: `packaging/linux/package_rpm_from_staging.sh`

**Interfaces:**
- Consumes: staging; requires `fpm` on PATH
- Produces: `dist/timerapp-exp-<ver>-amd64.rpm` (normalize name if fpm emits `.x86_64.rpm`)

- [ ] **Step 1: Implement RPM script**

```bash
#!/usr/bin/env bash
set -euo pipefail
# fpm -s dir -t rpm -C "$STAGING_DIR" \
#   --name timerapp-exp --version "$VERSION" --architecture x86_64 \
#   --description "..." --maintainer "..." \
#   --depends '...' (map from deb Depends best-effort) \
#   -p "$DIST_DIR/${PACKAGE_NAME}-${VERSION}-amd64.rpm" \
#   opt usr
```

If fpm writes `timerapp-exp-VERSION-1.x86_64.rpm`, rename/move to `timerapp-exp-${VERSION}-amd64.rpm`.

- [ ] **Step 2: Document CI fpm install** (used in Task 6)

```bash
sudo apt-get install -y ruby ruby-dev build-essential rpm
sudo gem install fpm --no-document
```

- [ ] **Step 3: Local smoke only if fpm installed; otherwise skip with note**

```bash
command -v fpm && ./packaging/linux/package_rpm_from_staging.sh
file dist/timerapp-exp-*-amd64.rpm
```

Expected when fpm present: `RPM` in `file` output.

- [ ] **Step 4: Commit**

```bash
git add packaging/linux/package_rpm_from_staging.sh
git commit -m "build: add rpm packaging from staging via fpm"
```

---

### Task 5: AppImage from onedir

**Files:**
- Create: `packaging/linux/package_appimage_from_onedir.sh`
- Create: `packaging/linux/appimage/timerapp-exp.desktop` (Exec=`TaskTimer`, Icon=`timerapp-exp`) if needed separate from `/usr` desktop

**Interfaces:**
- Consumes: `ONEDIR` (`dist/TaskTimer`), `VERSION`, `DIST_DIR`, tools dir for linuxdeploy/appimagetool
- Produces: `dist/timerapp-exp-<ver>-x86_64.AppImage`
- Env: `LINUXDEPLOY` / `APPIMAGETOOL` paths (CI downloads)

- [ ] **Step 1: Implement AppDir builder**

```bash
# AppDir/
#   AppRun -> usr/bin/TaskTimer or shell wrapper
#   usr/bin/TaskTimer + full onedir libs beside it (copy onedir into usr/lib/timerapp-exp or usr/bin tree)
#   timerapp-exp.desktop with Exec=TaskTimer
#   timerapp-exp.svg / .png
# Prefer: copy entire onedir to AppDir/usr/lib/timerapp-exp/ and AppRun exec that binary
# Then: "$LINUXDEPLOY" --appdir AppDir --desktop-file=... --icon-file=... 
#       "$APPIMAGETOOL" AppDir "$DIST_DIR/timerapp-exp-${VERSION}-x86_64.AppImage"
```

Pin download URLs in the script comments (continuous releases from linuxdeploy/appimagetool GitHub); CI Task 6 curls them.

- [ ] **Step 2: Smoke (CI or local with tools)**

```bash
test -x dist/timerapp-exp-*-x86_64.AppImage
file dist/timerapp-exp-*-x86_64.AppImage
# optional: ./dist/….AppImage --appimage-help  (or extract)
```

Expected: executable; `file` mentions ELF or ISO 9660 / AppImage.

- [ ] **Step 3: Commit**

```bash
git add packaging/linux/package_appimage_from_onedir.sh packaging/linux/appimage/
git commit -m "build: add AppImage packaging from PyInstaller onedir"
```

---

### Task 6: `build_linux_extra.sh` + CI job extension

**Files:**
- Create: `build_linux_extra.sh`
- Modify: `.github/workflows/ci.yml` job `build-deb`

**Interfaces:**
- `build_linux_extra.sh`: assumes `dist/TaskTimer` already built; stages once; calls rpm/tar/appimage scripts; writes all into `dist/`
- CI: after `./build_deb.sh`, run `./build_linux_extra.sh`; upload artifacts

- [ ] **Step 1: Write `build_linux_extra.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
# read VERSION from pyproject; require dist/TaskTimer
# STAGING_DIR=$(mktemp -d)
# stage_from_pyinstaller.sh
# package_tarballs_from_staging.sh
# package_rpm_from_staging.sh
# package_appimage_from_onedir.sh  # uses ONEDIR, not staging
# rm -rf STAGING_DIR
```

- [ ] **Step 2: Update CI `build-deb` job**

After existing deb build steps, add:

```yaml
- name: Install Linux extra packaging tools
  run: |
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends ruby ruby-dev build-essential rpm curl ca-certificates file
    sudo gem install fpm --no-document
    mkdir -p "$HOME/linuxdeploy"
    # curl -L pinned linuxdeploy + appimagetool into $HOME/linuxdeploy, chmod +x
    echo "LINUXDEPLOY=$HOME/linuxdeploy/linuxdeploy-x86_64.AppImage" >> "$GITHUB_ENV"
    echo "APPIMAGETOOL=$HOME/linuxdeploy/appimagetool-x86_64.AppImage" >> "$GITHUB_ENV"

- name: Build rpm, tarballs, AppImage
  run: ./build_linux_extra.sh

- uses: actions/upload-artifact@v5
  with:
    name: linux-packages
    path: |
      dist/timerapp-exp-*-amd64.deb
      dist/timerapp-exp-*-amd64.rpm
      dist/timerapp-exp-*-linux-amd64.tar.xz
      dist/timerapp-exp-*-linux-amd64.tgz
      dist/timerapp-exp-*-x86_64.AppImage
    if-no-files-found: error
```

Keep or replace the old single `deb-amd64` artifact upload so **all five** files are available (either one combined artifact `linux-packages` or five named uploads). Prefer one `linux-packages` folder for release download simplicity; update any release docs that say `deb-amd64` only.

- [ ] **Step 3: Push branch / watch CI**

```bash
gh run watch --exit-status
```

Expected: job success; five files in artifact.

- [ ] **Step 4: Commit**

```bash
git add build_linux_extra.sh .github/workflows/ci.yml
git commit -m "ci: build rpm, tar, and AppImage alongside deb"
```

---

### Task 7: Documentation and agent rule

**Files:**
- Modify: `docs/system-requirements.md`
- Modify: `docs/architecture-cross-platform.md`
- Modify: `README.md`
- Modify: `ИНСТРУКЦИЯ.md`
- Modify: `.cursor/rules/timerapp-ag-version-bump.mdc` (note: linux extras CI-only; local «собери» still deb-only)

- [ ] **Step 1: Update artifact tables to list deb/rpm/tar.xz/tgz/AppImage with `timerapp-exp-` names**

- [ ] **Step 2: Replace “Flatpak/AppImage не используются” with AppImage available; Flatpak/Snap — в планах**

- [ ] **Step 3: Commit**

```bash
git add README.md ИНСТРУКЦИЯ.md docs/system-requirements.md docs/architecture-cross-platform.md .cursor/rules/timerapp-ag-version-bump.mdc
git commit -m "docs: document Linux rpm/tar/AppImage CI artifacts"
```

---

### Task 8: Acceptance checklist

- [ ] **Step 1: Verify artifact names from CI download**

```text
timerapp-exp-<ver>-amd64.deb
timerapp-exp-<ver>-amd64.rpm
timerapp-exp-<ver>-linux-amd64.tar.xz
timerapp-exp-<ver>-linux-amd64.tgz
timerapp-exp-<ver>-x86_64.AppImage
```

- [ ] **Step 2: Smoke commands**

```bash
dpkg-deb -I …deb | head
file …rpm          # expect RPM
tar -tJf …tar.xz | head
tar -tzf …tgz | head
test -x …AppImage
```

- [ ] **Step 3: Confirm local `./build_deb.sh` still does not require fpm**

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| Shared staging from onedir | 1 |
| deb via staging; local deb-only | 2 |
| tar.xz + tgz + INSTALL | 3 |
| rpm via fpm, not alien | 4 |
| AppImage unsigned OK | 5 |
| Single CI PyInstaller path | 6 |
| Docs + CI-only extras rule | 7 |
| Acceptance criteria | 8 |
| Flatpak/snap deferred | Global Constraints / out of scope |

No open TBD placeholders; CI tool pin URLs to be filled with concrete release asset URLs when implementing Task 5–6 (choose current linuxdeploy continuous build URLs at implement time and paste into script).
