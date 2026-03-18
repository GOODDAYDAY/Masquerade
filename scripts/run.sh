#!/usr/bin/env bash
set -euo pipefail

# ========================================
#   Masquerade - AI Board Game Arena
#   Play + Record + Export MP4
#   One-click setup & run (Linux / macOS)
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="$PROJECT_ROOT/.venv"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

echo "========================================"
echo "  Masquerade - AI Board Game Arena"
echo "  Play + Record + Export MP4"
echo "========================================"
echo ""

# =====================================================================
# 1. Detect OS & package manager
# =====================================================================

OS="$(uname -s)"
DISTRO=""
PKG_INSTALL=""

detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        PKG_INSTALL="sudo apt-get install -y"
        DISTRO="debian"
    elif command -v dnf &>/dev/null; then
        PKG_INSTALL="sudo dnf install -y"
        DISTRO="fedora"
    elif command -v yum &>/dev/null; then
        PKG_INSTALL="sudo yum install -y"
        DISTRO="centos"
    elif command -v pacman &>/dev/null; then
        PKG_INSTALL="sudo pacman -S --noconfirm"
        DISTRO="arch"
    elif command -v brew &>/dev/null; then
        PKG_INSTALL="brew install"
        DISTRO="brew"
    elif command -v apk &>/dev/null; then
        PKG_INSTALL="sudo apk add --no-cache"
        DISTRO="alpine"
    fi
}

detect_pkg_manager

# =====================================================================
# 2. Check / Install Python >= 3.11
# =====================================================================

PYTHON=""

find_python() {
    for cmd in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
            if [[ -n "$ver" ]]; then
                local major minor
                major="${ver%%.*}"
                minor="${ver#*.}"
                if (( major == 3 && minor >= 11 )); then
                    PYTHON="$cmd"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

if find_python; then
    ok "Python found: $PYTHON ($($PYTHON --version 2>&1))"
else
    warn "Python >= 3.11 not found, attempting to install..."
    if [[ -n "$PKG_INSTALL" ]]; then
        case "$DISTRO" in
            debian)
                sudo apt-get update -qq
                $PKG_INSTALL python3.11 python3.11-venv python3-pip 2>/dev/null \
                || $PKG_INSTALL python3 python3-venv python3-pip
                ;;
            fedora)  $PKG_INSTALL python3.11 python3-pip 2>/dev/null || $PKG_INSTALL python3 python3-pip ;;
            centos)  $PKG_INSTALL python3.11 python3-pip 2>/dev/null || $PKG_INSTALL python3 python3-pip ;;
            arch)    $PKG_INSTALL python python-pip ;;
            brew)    brew install python@3.11 || brew install python@3.12 || brew install python ;;
            alpine)  $PKG_INSTALL python3 py3-pip python3-dev ;;
        esac
        find_python || fail "Could not install Python >= 3.11. Please install it manually."
        ok "Python installed: $PYTHON"
    else
        fail "No supported package manager found. Please install Python >= 3.11 manually."
    fi
fi

# =====================================================================
# 3. Check / Install Node.js >= 18
# =====================================================================

NODE_MIN_VERSION=18

check_node_version() {
    if command -v node &>/dev/null; then
        local ver
        ver="$(node -v 2>/dev/null | sed 's/^v//')"
        local major="${ver%%.*}"
        if (( major >= NODE_MIN_VERSION )); then
            return 0
        fi
    fi
    return 1
}

if check_node_version; then
    ok "Node.js found: $(node -v)"
else
    warn "Node.js >= $NODE_MIN_VERSION not found, attempting to install..."
    if [[ "$OS" == "Linux" ]]; then
        # Use NodeSource setup if available, otherwise try package manager
        if command -v curl &>/dev/null; then
            info "Installing Node.js 20.x via NodeSource..."
            curl -fsSL https://deb.nodesource.com/setup_20.x 2>/dev/null | sudo -E bash - 2>/dev/null \
            && sudo apt-get install -y nodejs 2>/dev/null \
            || {
                # Fallback: try package manager directly
                if [[ -n "$PKG_INSTALL" ]]; then
                    $PKG_INSTALL nodejs npm 2>/dev/null || true
                fi
            }
        elif [[ -n "$PKG_INSTALL" ]]; then
            $PKG_INSTALL nodejs npm 2>/dev/null || true
        fi
    elif [[ "$OS" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            brew install node@20 || brew install node
        else
            fail "Please install Homebrew first (https://brew.sh) or install Node.js >= $NODE_MIN_VERSION manually."
        fi
    fi
    check_node_version || fail "Could not install Node.js >= $NODE_MIN_VERSION. Please install it manually."
    ok "Node.js installed: $(node -v)"
fi

# =====================================================================
# 4. Check / Install ffmpeg (for video encoding)
# =====================================================================

if command -v ffmpeg &>/dev/null; then
    ok "ffmpeg found: $(ffmpeg -version 2>&1 | head -1)"
else
    warn "ffmpeg not found, attempting to install..."
    if [[ -n "$PKG_INSTALL" ]]; then
        $PKG_INSTALL ffmpeg 2>/dev/null || true
    fi
    if command -v ffmpeg &>/dev/null; then
        ok "ffmpeg installed"
    else
        warn "ffmpeg not available — video re-encoding will use CPU fallback"
    fi
fi

# =====================================================================
# 5. Setup Python virtual environment & install dependencies
# =====================================================================

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating Python virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    ok "Virtual environment created at $VENV_DIR"
fi

# Activate venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Upgrade pip quietly, then install project
info "Installing Python dependencies..."
pip install --upgrade pip -q 2>/dev/null
pip install -e ".[render]" -q 2>/dev/null
ok "Python dependencies ready"

# =====================================================================
# 6. Install frontend (Node) dependencies
# =====================================================================

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    info "Installing frontend dependencies..."
    (cd "$FRONTEND_DIR" && npm install --prefer-offline 2>/dev/null)
    ok "Frontend dependencies installed"
else
    ok "Frontend dependencies already installed"
fi

# =====================================================================
# 7. Check .env file
# =====================================================================

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
        warn "No .env file found. Copying from .env.example..."
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        warn "Please edit .env and set your API key before running!"
        echo ""
        cat "$PROJECT_ROOT/.env.example"
        echo ""
        read -rp "Press Enter to continue after editing .env (or Ctrl+C to abort)..."
    else
        warn "No .env file found. Make sure your API keys are configured."
    fi
fi

echo ""
echo "========================================"
echo "  Environment Ready — Starting Game"
echo "========================================"
echo ""

# =====================================================================
# 8. List game types & prompt for selection
# =====================================================================

python -m backend.main --list
echo ""

read -rp "Select game type: " GAME
if [[ -z "$GAME" ]]; then
    fail "No game selected."
fi

echo ""

# =====================================================================
# 9. Run the game
# =====================================================================

python -m backend.main "$GAME"

# =====================================================================
# 10. Find the latest script file
# =====================================================================

SCRIPTS_DIR="$PROJECT_ROOT/output/scripts"
SCRIPT_FILE=""

if [[ -d "$SCRIPTS_DIR" ]]; then
    # Find latest game script matching the selected game type
    SCRIPT_FILE="$(ls -t "$SCRIPTS_DIR"/game_"${GAME}"_*.json 2>/dev/null | head -1 || true)"
fi

if [[ -z "$SCRIPT_FILE" || ! -f "$SCRIPT_FILE" ]]; then
    fail "Could not find script file for game type: $GAME"
fi

SCRIPT_FILENAME="$(basename "$SCRIPT_FILE")"
echo ""
echo "Script: $SCRIPT_FILENAME"

# =====================================================================
# 11. Generate TTS audio
# =====================================================================

echo ""
echo "Generating TTS audio..."
python -m backend.tts.generate "$SCRIPT_FILE"

# =====================================================================
# 12. Render video via Remotion
# =====================================================================

echo ""
node scripts/render-video.mjs "$SCRIPT_FILENAME"

echo ""
echo "========================================"
echo "  All Done!"
echo "========================================"
