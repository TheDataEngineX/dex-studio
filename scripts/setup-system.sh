#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DEX Studio — System Dependencies Installer
# ---------------------------------------------------------------------------
# Installs all Linux/macOS system-level packages required to develop and
# run DEX Studio, including the pywebview native-window backend (GTK/WebKit
# on Linux, WebKit on macOS — bundled).
#
# Usage:
#   uv run poe setup-system          # via poe task (recommended)
#   bash scripts/setup-system.sh     # direct execution
#
# Supports: Ubuntu/Debian, Fedora/RHEL, Arch Linux, macOS (Homebrew)
# ---------------------------------------------------------------------------

set -euo pipefail

# ── Colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

# ── Sudo pre-check ─────────────────────────────────────────────────────────
ensure_sudo() {
    if [[ "$OS" == "macos" ]]; then
        return 0  # Homebrew doesn't need sudo
    fi

    if [[ $EUID -eq 0 ]]; then
        return 0  # Already root
    fi

    # Not root — print the command and exit
    echo ""
    warn "This script needs root to install system packages."
    echo ""
    info "Run directly:"
    echo ""
    echo "    sudo bash scripts/setup-system.sh"
    echo ""
    exit 1
}

# ── Detect OS / package manager ────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif command -v apt-get &>/dev/null; then
        OS="debian"
    elif command -v dnf &>/dev/null; then
        OS="fedora"
    elif command -v pacman &>/dev/null; then
        OS="arch"
    else
        fail "Unsupported OS. Install the packages listed below manually."
        echo ""
        echo "Required packages:"
        echo "  - git, curl, build tools (gcc, make)"
        echo "  - Python 3.11+"
        echo "  - GTK 3/4 + WebKitGTK + PyGObject (for pywebview native mode)"
        echo ""
        echo "  OR skip native mode and run in browser:"
        echo "    dex-studio --no-native"
        echo ""
        exit 1
    fi
}

# ── Package lists per OS ───────────────────────────────────────────────────

install_debian() {
    info "Updating apt package index..."
    sudo apt-get update -qq

    info "Installing core build tools..."
    sudo apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        build-essential \
        libffi-dev \
        libssl-dev \
        pkg-config

    info "Installing GTK + WebKitGTK + PyGObject (pywebview backend)..."
    sudo apt-get install -y --no-install-recommends \
        python3-gi \
        python3-gi-cairo \
        gir1.2-gtk-3.0 \
        gir1.2-webkit2-4.1 \
        libgirepository1.0-dev \
        libcairo2-dev

    info "Installing additional Python development headers..."
    sudo apt-get install -y --no-install-recommends \
        python3-dev
}

install_fedora() {
    info "Installing core build tools..."
    sudo dnf install -y \
        git \
        curl \
        gcc \
        gcc-c++ \
        make \
        libffi-devel \
        openssl-devel \
        pkg-config

    info "Installing GTK + WebKitGTK + PyGObject (pywebview backend)..."
    sudo dnf install -y \
        python3-gobject \
        gtk3 \
        webkit2gtk4.1 \
        gobject-introspection-devel \
        cairo-gobject-devel

    info "Installing additional Python development headers..."
    sudo dnf install -y \
        python3-devel
}

install_arch() {
    info "Installing core build tools..."
    sudo pacman -Syu --noconfirm \
        git \
        curl \
        base-devel \
        openssl \
        pkgconf

    info "Installing GTK + WebKitGTK + PyGObject (pywebview backend)..."
    sudo pacman -S --noconfirm \
        python-gobject \
        gtk3 \
        webkit2gtk-4.1 \
        gobject-introspection \
        cairo
}

install_macos() {
    if ! command -v brew &>/dev/null; then
        fail "Homebrew not found. Install from https://brew.sh"
        exit 1
    fi

    info "Installing core packages via Homebrew..."
    brew install git curl

    # macOS uses native WebKit — no GTK needed
    # pywebview uses pyobjc (installed via pip/uv as a Python dependency)
    info "Installing PyObjC bridge for macOS native window..."
    ok "macOS uses built-in WebKit — no GTK/QT needed for pywebview"
    ok "pyobjc will be installed automatically via 'uv sync'"
}

# ── Install uv (if not present) ───────────────────────────────────────────
install_uv() {
    # Check as the real user, not root
    local real_user="${SUDO_USER:-$USER}"

    if command -v uv &>/dev/null; then
        ok "uv already installed ($(uv --version))"
        return 0
    fi

    # Also check the real user's PATH (uv installs to ~/.local/bin)
    local user_uv="$(eval echo ~"$real_user")/.local/bin/uv"
    if [[ -x "$user_uv" ]]; then
        ok "uv already installed at $user_uv"
        return 0
    fi

    info "Installing uv for user $real_user..."
    if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" ]]; then
        # Running as root via sudo — install as the calling user so uv
        # lands in ~user/.local/bin, not /root/.local/bin
        sudo -u "$SUDO_USER" bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    ok "uv installed"
}

# ── Python deps ────────────────────────────────────────────────────────────
install_python_deps() {
    echo ""
    local real_user="${SUDO_USER:-$USER}"
    local user_uv="$(eval echo ~"$real_user")/.local/bin/uv"

    # Resolve a working uv binary (might not be in root's PATH)
    local uv_bin=""
    if command -v uv &>/dev/null; then
        uv_bin="uv"
    elif [[ -x "$user_uv" ]]; then
        uv_bin="$user_uv"
    fi

    if [[ -z "$uv_bin" ]]; then
        warn "uv not found — run 'curl -LsSf https://astral.sh/uv/install.sh | sh' then 'uv sync'"
        return 0
    fi

    info "Installing Python dependencies via uv..."
    if [[ $EUID -eq 0 && -n "${SUDO_USER:-}" ]]; then
        # Run uv sync as the real user so deps go into the project venv, not root's
        sudo -u "$SUDO_USER" "$uv_bin" sync --all-groups
    else
        "$uv_bin" sync --all-groups
    fi
    ok "Python dependencies installed"
}

# ── Verification ───────────────────────────────────────────────────────────
verify() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "Verifying installation..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    local status=0
    local real_user="${SUDO_USER:-$USER}"
    local user_uv="$(eval echo ~"$real_user")/.local/bin/uv"

    # Required tools
    for cmd in git curl python3; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" --version 2>&1 | head -1)
            ok "$cmd — $ver"
        else
            fail "$cmd — NOT FOUND"
            status=1
        fi
    done

    # uv — check both system PATH and user's ~/.local/bin
    if command -v uv &>/dev/null; then
        ok "uv — $(uv --version 2>&1 | head -1)"
    elif [[ -x "$user_uv" ]]; then
        ok "uv — $("$user_uv" --version 2>&1 | head -1) (at $user_uv)"
    else
        fail "uv — NOT FOUND"
        status=1
    fi

    # Python version check
    python_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
    if [[ "$python_ver" < "3.11" ]]; then
        fail "Python $python_ver found — requires 3.11+"
        status=1
    else
        ok "Python version — $python_ver"
    fi

    # pywebview native backend check
    if [[ "$OS" != "macos" ]]; then
        if python3 -c "import gi" &>/dev/null 2>&1; then
            ok "PyGObject (gi) — available"
        else
            warn "PyGObject (gi) — not importable (native mode will fall back to browser)"
        fi
    else
        ok "macOS — native WebKit available"
    fi

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [[ $status -eq 0 ]]; then
        echo ""
        ok "All system dependencies installed!"
        echo ""
        info "Next steps:"
        echo "  1. uv sync                        # Install Python deps"
        echo "  2. uv run poe check-all            # Verify everything works"
        echo "  3. uv run dex-studio               # Launch DEX Studio"
        echo "  4. uv run dex-studio --no-native   # Launch in browser mode"
        echo ""
    else
        echo ""
        fail "Some dependencies are missing — see above"
        exit 1
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║       DEX Studio — System Dependencies Installer               ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""

    detect_os
    info "Detected OS: $OS"
    echo ""

    ensure_sudo

    case "$OS" in
        debian) install_debian ;;
        fedora) install_fedora ;;
        arch)   install_arch ;;
        macos)  install_macos ;;
    esac

    install_uv
    install_python_deps
    verify
}

main "$@"
