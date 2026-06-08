#!/usr/bin/env bash
# Spectral — user-space installer (no sudo required)
#
# One-liner install:
#   curl -sSL https://raw.githubusercontent.com/eisenkult/spectral/main/install.sh | bash
#
# After install, launch from the install directory:
#   cd ~/.local/share/spectral && .venv/bin/python main.py ~/Music
# Or use the launcher (if ~/.local/bin is in your PATH):
#   spectral ~/Music

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────
REPO_URL="https://github.com/eisenkult/spectral.git"
INSTALL_DIR="${HOME}/.local/share/spectral"
BIN_DIR="${HOME}/.local/bin"
MIN_PY_MAJOR=3
MIN_PY_MINOR=9

# ── colour helpers ─────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  _g='\033[1;32m' _y='\033[1;33m' _r='\033[1;31m' _b='\033[1;34m' _0='\033[0m'
else
  _g='' _y='' _r='' _b='' _0=''
fi
say()  { printf "${_g}==>${_0} %s\n" "$*"; }
info() { printf "${_b}  ->${_0} %s\n" "$*"; }
warn() { printf "${_y}warn:${_0} %s\n" "$*" >&2; }
die()  { printf "${_r}error:${_0} %s\n" "$*" >&2; exit 1; }

# ── platform detection ────────────────────────────────────────────────────────
is_termux() {
  [ -n "${TERMUX_VERSION:-}" ] || [ -d /data/data/com.termux ]
}

detect_platform() {
  if is_termux; then
    PLATFORM=termux
  elif uname -s | grep -qi darwin; then
    PLATFORM=macos
  elif command -v apt-get >/dev/null 2>&1; then
    PLATFORM=debian
  elif command -v pacman >/dev/null 2>&1; then
    PLATFORM=arch
  elif command -v dnf >/dev/null 2>&1; then
    PLATFORM=fedora
  else
    PLATFORM=unknown
  fi
}

# ── python check ──────────────────────────────────────────────────────────────
check_python() {
  PYTHON=""
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      if "$cmd" -c "
import sys
major, minor = sys.version_info[:2]
if major < ${MIN_PY_MAJOR} or (major == ${MIN_PY_MAJOR} and minor < ${MIN_PY_MINOR}):
    sys.exit(1)
" 2>/dev/null; then
        PYTHON="$cmd"
        break
      fi
    fi
  done

  if [ -z "$PYTHON" ]; then
    warn "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ not found."
    case "$PLATFORM" in
      termux)  die "Install Python with:  pkg install python" ;;
      debian)  die "Install Python with:  sudo apt install python3 python3-venv python3-pip" ;;
      arch)    die "Install Python with:  sudo pacman -S python" ;;
      fedora)  die "Install Python with:  sudo dnf install python3" ;;
      macos)   die "Install Python from https://python.org  or:  brew install python" ;;
      *)       die "Please install Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ and re-run." ;;
    esac
  fi

  say "Python: $($PYTHON --version)"
}

# ── venv availability check ───────────────────────────────────────────────────
check_venv() {
  if ! "$PYTHON" -m venv --help >/dev/null 2>&1; then
    case "$PLATFORM" in
      debian) die "venv module missing. Install with:  sudo apt install python3-venv" ;;
      *)      die "Python venv module not available. Please reinstall Python." ;;
    esac
  fi
}

# ── git check ─────────────────────────────────────────────────────────────────
check_git() {
  if ! command -v git >/dev/null 2>&1; then
    case "$PLATFORM" in
      termux) die "Install git with:  pkg install git" ;;
      debian) die "Install git with:  sudo apt install git" ;;
      arch)   die "Install git with:  sudo pacman -S git" ;;
      fedora) die "Install git with:  sudo dnf install git" ;;
      macos)  die "Install git with:  xcode-select --install" ;;
      *)      die "Please install git and re-run." ;;
    esac
  fi
}

# ── Termux: PortAudio (required by sounddevice) ───────────────────────────────
ensure_portaudio_termux() {
  say "Ensuring portaudio is installed (required for audio playback)…"
  pkg install -y portaudio 2>/dev/null || warn "pkg install portaudio failed — audio may not work."
}

# ── Linux: warn if libportaudio2 is missing ───────────────────────────────────
check_portaudio_linux() {
  # sounddevice ships its own PortAudio on macOS/Windows but not Linux
  if ! (ldconfig -p 2>/dev/null | grep -q libportaudio || \
        find /usr /lib /lib64 -name 'libportaudio*' 2>/dev/null | grep -q .); then
    warn "libportaudio not detected. If audio fails, install it:"
    case "$PLATFORM" in
      debian) warn "  sudo apt install libportaudio2" ;;
      arch)   warn "  sudo pacman -S portaudio" ;;
      fedora) warn "  sudo dnf install portaudio" ;;
      *)      warn "  Install portaudio from your package manager." ;;
    esac
  fi
}

# ── clone or update repo ──────────────────────────────────────────────────────
fetch_repo() {
  if [ -d "${INSTALL_DIR}/.git" ]; then
    say "Updating existing installation at ${INSTALL_DIR}…"
    git -C "${INSTALL_DIR}" pull --ff-only
  else
    say "Cloning Spectral into ${INSTALL_DIR}…"
    mkdir -p "$(dirname "${INSTALL_DIR}")"
    git clone --depth=1 "${REPO_URL}" "${INSTALL_DIR}"
  fi
}

# ── create venv and install Python deps ──────────────────────────────────────
setup_venv() {
  VENV_DIR="${INSTALL_DIR}/.venv"
  say "Creating virtual environment…"
  "$PYTHON" -m venv "${VENV_DIR}"

  say "Installing Python dependencies…"
  "${VENV_DIR}/bin/pip" install --upgrade pip --quiet
  "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
}

# ── write ~/.local/bin/spectral launcher ─────────────────────────────────────
write_launcher() {
  mkdir -p "${BIN_DIR}"
  cat > "${BIN_DIR}/spectral" <<LAUNCHER
#!/usr/bin/env bash
exec "${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/main.py" "\$@"
LAUNCHER
  chmod +x "${BIN_DIR}/spectral"
  info "Launcher: ${BIN_DIR}/spectral"
}

# ── PATH hint ─────────────────────────────────────────────────────────────────
path_hint() {
  case ":${PATH}:" in
    *":${BIN_DIR}:"*) return ;;
  esac

  warn "${BIN_DIR} is not in PATH — the 'spectral' command won't work yet."

  # Detect the user's login shell RC file
  case "${SHELL:-}" in
    */zsh)  RC="${ZDOTDIR:-${HOME}}/.zshrc" ;;
    */fish) RC="${HOME}/.config/fish/config.fish" ;;
    *)      RC="${HOME}/.bashrc" ;;
  esac

  if [ "${SHELL:-}" = "*/fish" ]; then
    warn "Add to PATH:  fish_add_path ${BIN_DIR}"
  else
    warn "Add to PATH:  echo 'export PATH=\"\${HOME}/.local/bin:\${PATH}\"' >> ${RC}"
    warn "Then reload:  source ${RC}"
  fi
}

# ── tmux / Android compatibility note ────────────────────────────────────────
termux_notes() {
  echo
  echo "  Termux / Android notes:"
  echo "  - Run inside tmux for the best experience (pkg install tmux)"
  echo "  - Textual works correctly with TERM=screen-256color set by tmux"
  echo "  - If audio is silent, ensure no other app holds the audio focus"
  echo "  - On some devices you may need the Termux:API companion app"
  echo "  - Keyboard shortcuts use the Termux extra-keys row for Ctrl/Alt"
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
  say "Spectral installer"
  detect_platform
  info "Platform: ${PLATFORM}"

  check_python
  check_venv
  check_git

  if is_termux; then
    ensure_portaudio_termux
  elif [ "${PLATFORM}" != "macos" ]; then
    check_portaudio_linux
  fi

  fetch_repo
  setup_venv
  write_launcher
  path_hint

  say "Done!"
  echo
  echo "  Launch anywhere (after adding ~/.local/bin to PATH):"
  echo "    spectral ~/Music"
  echo
  echo "  Or launch directly from the install directory:"
  echo "    cd ${INSTALL_DIR} && .venv/bin/python main.py ~/Music"
  echo
  if is_termux; then
    termux_notes
  fi
}

main "$@"
