#!/usr/bin/env bash
# Idempotent Ubuntu setup script for the academic paper pipeline.
# Installs system packages, Quarto CLI, TinyTeX, and required LaTeX packages.

set -euo pipefail

UPGRADE_QUARTO=false
if [[ "${1:-}" == "--upgrade" ]]; then
  UPGRADE_QUARTO=true
fi

log_info() { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
log_ok()   { printf '\033[1;32m[OK]\033[0m   %s\n' "$*"; }
log_warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
log_err()  { printf '\033[1;31m[ERR]\033[0m  %s\n' "$*" >&2; }

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    log_err "sudo is required when not running as root."
    exit 1
  fi
fi

detect_arch() {
  local arch=""
  if command -v dpkg >/dev/null 2>&1; then
    arch="$(dpkg --print-architecture)"
  else
    case "$(uname -m)" in
      x86_64)  arch="amd64" ;;
      aarch64) arch="arm64" ;;
      *)       arch="$(uname -m)" ;;
    esac
  fi

  case "$arch" in
    amd64|arm64) printf '%s' "$arch" ;;
    *)
      log_err "Unsupported architecture: '$arch' (expected amd64 or arm64)."
      exit 1
      ;;
  esac
}

ARCH="$(detect_arch)"
log_info "Detected Linux architecture: $ARCH"

# System dependencies
APT_PACKAGES=(
  curl
  wget
  perl
  xz-utils
  fontconfig
  poppler-utils
  python3
  python3-pil
  zip
)

MISSING_APT=()
for pkg in "${APT_PACKAGES[@]}"; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    MISSING_APT+=("$pkg")
  fi
done

if [[ "${#MISSING_APT[@]}" -gt 0 ]]; then
  log_info "Installing missing apt packages: ${MISSING_APT[*]}"
  $SUDO apt-get update -qq
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends "${MISSING_APT[@]}"
  log_ok "System packages installed."
else
  log_ok "All required apt packages are already installed."
fi

# Quarto CLI
fetch_latest_quarto_version() {
  local ver=""
  ver="$(
    curl -fsSL "https://quarto.org/docs/download/_download.json" 2>/dev/null \
      | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null || true
  )"
  if [[ -z "$ver" ]]; then
    ver="$(
      curl -fsSL "https://api.github.com/repos/quarto-dev/quarto-cli/releases/latest" 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'].lstrip('v'))" 2>/dev/null || true
    )"
  fi
  printf '%s' "$ver"
}

install_quarto_deb() {
  local version="$1"
  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' RETURN

  local deb_name="quarto-${version}-linux-${ARCH}.deb"
  local deb_url="https://github.com/quarto-dev/quarto-cli/releases/download/v${version}/${deb_name}"

  log_info "Downloading Quarto v${version} (${ARCH})..."
  curl -fL --retry 3 --progress-bar "$deb_url" -o "${tmpdir}/${deb_name}"

  log_info "Installing ${deb_name}..."
  if ! $SUDO dpkg -i "${tmpdir}/${deb_name}"; then
    log_info "Resolving package dependencies via apt-get -f install..."
    $SUDO apt-get install -f -y
  fi
}

if command -v quarto >/dev/null 2>&1; then
  CURRENT_QUARTO="$(quarto --version)"
  if [[ "$UPGRADE_QUARTO" == true ]]; then
    LATEST_QUARTO="$(fetch_latest_quarto_version)"
    if [[ -n "$LATEST_QUARTO" && "$CURRENT_QUARTO" != "$LATEST_QUARTO" ]]; then
      install_quarto_deb "$LATEST_QUARTO"
      log_ok "Upgraded Quarto to $(quarto --version)."
    else
      log_ok "Quarto ${CURRENT_QUARTO} is already up to date."
    fi
  else
    log_ok "Quarto ${CURRENT_QUARTO} already installed (pass --upgrade to check for newer releases)."
  fi
else
  LATEST_QUARTO="$(fetch_latest_quarto_version)"
  if [[ -z "$LATEST_QUARTO" ]]; then
    log_err "Could not determine latest Quarto version from quarto.org or GitHub API."
    exit 1
  fi
  install_quarto_deb "$LATEST_QUARTO"
  log_ok "Quarto $(quarto --version) installed."
fi

# TinyTeX
locate_tinytex_bin() {
  local dir
  for dir in \
    "$HOME/.TinyTeX/bin/x86_64-linux" \
    "$HOME/.TinyTeX/bin/aarch64-linux" \
    "$HOME/.TinyTeX/bin/"*-linux; do
    if [[ -x "${dir}/tlmgr" ]]; then
      printf '%s' "$dir"
      return 0
    fi
  done
  return 1
}

TINYTEX_BIN=""
if TINYTEX_BIN="$(locate_tinytex_bin)"; then
  export PATH="${TINYTEX_BIN}:${PATH}"
  log_ok "TinyTeX found at ${TINYTEX_BIN}."
elif command -v pdflatex >/dev/null 2>&1 && command -v tlmgr >/dev/null 2>&1; then
  log_ok "System TeX distribution found ($(command -v pdflatex))."
else
  log_info "Installing TinyTeX via Quarto..."
  if ! quarto install tinytex --no-prompt --update-path; then
    log_warn "Falling back to TinyTeX install without system symlink update..."
    quarto install tinytex --no-prompt
  fi
  if TINYTEX_BIN="$(locate_tinytex_bin)"; then
    export PATH="${TINYTEX_BIN}:${PATH}"
    log_ok "TinyTeX installed at ${TINYTEX_BIN}."
  else
    log_warn "TinyTeX installed; checking PATH..."
  fi
fi

if [[ -n "${TINYTEX_BIN:-}" && -f "$HOME/.bashrc" ]]; then
  PATH_LINE="export PATH=\"${TINYTEX_BIN}:\$PATH\""
  if ! grep -Fq "$TINYTEX_BIN" "$HOME/.bashrc"; then
    {
      echo ""
      echo "# Added by setup_ubuntu.sh for TinyTeX"
      echo "$PATH_LINE"
    } >> "$HOME/.bashrc"
    log_info "Appended TinyTeX bin directory to ~/.bashrc."
  fi
fi

# LaTeX packages
declare -A TEX_STY_TO_PKG=(
  ["amsmath.sty"]="amsmath"
  ["amssymb.sty"]="amsfonts"
  ["amsthm.sty"]="amscls"
  ["mathtools.sty"]="mathtools"
  ["bm.sty"]="tools"
  ["algorithm.sty"]="algorithms"
  ["algpseudocode.sty"]="algorithmicx"
  ["algorithm2e.sty"]="algorithm2e"
  ["ifoddpage.sty"]="ifoddpage"
  ["relsize.sty"]="relsize"
  ["booktabs.sty"]="booktabs"
  ["tabularx.sty"]="tabularx"
  ["multirow.sty"]="multirow"
  ["graphicx.sty"]="graphics"
  ["subcaption.sty"]="caption"
  ["float.sty"]="float"
  ["cleveref.sty"]="cleveref"
  ["hyperref.sty"]="hyperref"
  ["nameref.sty"]="nameref"
  ["xcolor.sty"]="xcolor"
  ["siunitx.sty"]="siunitx"
  ["translations.sty"]="translations"
  ["lmodern.sty"]="lm"
  ["t1enc.def"]="ec"
  ["microtype.sty"]="microtype"
  ["geometry.sty"]="geometry"
  ["scrartcl.cls"]="koma-script"
  ["framed.sty"]="framed"
  ["fvextra.sty"]="fvextra"
  ["tcolorbox.sty"]="tcolorbox"
  ["upquote.sty"]="upquote"
  ["etoolbox.sty"]="etoolbox"
  ["bookmark.sty"]="bookmark"
)

if command -v tlmgr >/dev/null 2>&1; then
  MISSING_TEX_PKGS=()
  declare -A SEEN_PKGS=()

  if command -v kpsewhich >/dev/null 2>&1; then
    for resource in "${!TEX_STY_TO_PKG[@]}"; do
      if ! kpsewhich "$resource" >/dev/null 2>&1; then
        pkg="${TEX_STY_TO_PKG[$resource]}"
        if [[ -z "${SEEN_PKGS[$pkg]:-}" ]]; then
          MISSING_TEX_PKGS+=("$pkg")
          SEEN_PKGS["$pkg"]=1
        fi
      fi
    done
  fi

  if ! command -v latexmk >/dev/null 2>&1; then
    MISSING_TEX_PKGS+=("latexmk")
  fi

  if [[ "${#MISSING_TEX_PKGS[@]}" -gt 0 ]]; then
    log_info "Installing missing TeX Live packages via tlmgr: ${MISSING_TEX_PKGS[*]}"
    tlmgr update --self || log_warn "tlmgr self-update skipped or already current."
    if ! tlmgr install "${MISSING_TEX_PKGS[@]}"; then
      log_warn "Batch tlmgr install had an issue; installing packages individually..."
      for pkg in "${MISSING_TEX_PKGS[@]}"; do
        tlmgr install "$pkg" || log_warn "Could not install optional TeX package: $pkg"
      done
    fi
    log_ok "LaTeX package installation complete."
  else
    log_ok "All required LaTeX packages are already installed."
  fi
else
  log_warn "tlmgr not found; skipping TeX Live package check."
fi

echo ""
log_info "Environment verification:"
printf '  - Quarto   : %s\n' "$(quarto --version 2>/dev/null || echo 'missing')"
printf '  - pdfLaTeX : %s\n' "$(pdflatex --version 2>/dev/null | head -n1 || echo 'missing')"
printf '  - Poppler  : %s\n' "$(pdfinfo -v 2>&1 | head -n1 || echo 'missing')"
printf '  - Python   : %s\n' "$(python3 --version 2>/dev/null || echo 'missing')"
PIL_VER="$(python3 -c 'import PIL; print(PIL.__version__)' 2>/dev/null || /usr/bin/python3 -c 'import PIL; print(PIL.__version__)' 2>/dev/null || echo 'missing')"
printf '  - Pillow   : %s\n' "$PIL_VER"
echo ""
log_ok "Setup complete. Run 'make build' to compile the manuscript."
