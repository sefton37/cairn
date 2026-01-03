#!/usr/bin/env bash
# ReOS Installer
#
# One-command installation for ReOS - the local-first Linux AI companion.
#
# Usage:
#   curl -fsSL https://get.reos.dev | bash
#   # or
#   git clone https://github.com/yourorg/reos && cd reos && ./install.sh
#
# Options:
#   --no-gui        Skip GUI dependencies (CLI only)
#   --no-shell      Skip shell integration
#   --prefix PATH   Install to PATH (default: /usr/local)
#   --user          Install to ~/.local (no sudo required)
#   --uninstall     Remove ReOS from system
#
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Defaults
INSTALL_GUI=true
INSTALL_SHELL=true
INSTALL_PREFIX="/usr/local"
USER_INSTALL=false
UNINSTALL=false

# Detect script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-gui)
            INSTALL_GUI=false
            shift
            ;;
        --no-shell)
            INSTALL_SHELL=false
            shift
            ;;
        --prefix)
            INSTALL_PREFIX="$2"
            shift 2
            ;;
        --user)
            USER_INSTALL=true
            INSTALL_PREFIX="$HOME/.local"
            shift
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --help|-h)
            cat <<'EOF'
ReOS Installer

Usage:
  ./install.sh [OPTIONS]

Options:
  --no-gui        Skip GUI dependencies (CLI only)
  --no-shell      Skip shell integration
  --prefix PATH   Install to PATH (default: /usr/local)
  --user          Install to ~/.local (no sudo required)
  --uninstall     Remove ReOS from system
  --help          Show this help

Examples:
  ./install.sh                    # Full installation with GUI
  ./install.sh --user             # User-local installation (no sudo)
  ./install.sh --no-gui           # CLI-only installation
  ./install.sh --uninstall        # Remove ReOS
EOF
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}" >&2
            exit 1
            ;;
    esac
done

#------------------------------------------------------------------------------
# Utility Functions
#------------------------------------------------------------------------------

log() {
    echo -e "${CYAN}[ReOS]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[ReOS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[ReOS]${NC} $*"
}

log_error() {
    echo -e "${RED}[ReOS]${NC} $*" >&2
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

require_command() {
    if ! command_exists "$1"; then
        log_error "Required command not found: $1"
        log_error "$2"
        exit 1
    fi
}

maybe_sudo() {
    if [[ "$USER_INSTALL" == true ]]; then
        "$@"
    elif [[ $EUID -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

#------------------------------------------------------------------------------
# Distro Detection
#------------------------------------------------------------------------------

detect_distro() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "$ID"
    elif command_exists lsb_release; then
        lsb_release -si | tr '[:upper:]' '[:lower:]'
    elif [[ -f /etc/debian_version ]]; then
        echo "debian"
    elif [[ -f /etc/fedora-release ]]; then
        echo "fedora"
    elif [[ -f /etc/arch-release ]]; then
        echo "arch"
    else
        echo "unknown"
    fi
}

detect_distro_family() {
    local distro="$1"
    case "$distro" in
        ubuntu|debian|linuxmint|pop|elementary|zorin|kali)
            echo "debian"
            ;;
        fedora|rhel|centos|rocky|alma|nobara)
            echo "fedora"
            ;;
        arch|manjaro|endeavouros|garuda)
            echo "arch"
            ;;
        opensuse*|suse*)
            echo "suse"
            ;;
        alpine)
            echo "alpine"
            ;;
        nixos)
            echo "nix"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

#------------------------------------------------------------------------------
# Dependency Installation
#------------------------------------------------------------------------------

install_python_debian() {
    log "Installing Python 3.12+ on Debian/Ubuntu..."
    maybe_sudo apt-get update -qq
    maybe_sudo apt-get install -y python3 python3-pip python3-venv python3-dev
}

install_python_fedora() {
    log "Installing Python 3.12+ on Fedora/RHEL..."
    maybe_sudo dnf install -y python3 python3-pip python3-devel
}

install_python_arch() {
    log "Installing Python 3.12+ on Arch..."
    maybe_sudo pacman -Sy --noconfirm python python-pip
}

install_python_suse() {
    log "Installing Python 3.12+ on openSUSE..."
    maybe_sudo zypper install -y python3 python3-pip python3-devel
}

install_python_alpine() {
    log "Installing Python 3.12+ on Alpine..."
    maybe_sudo apk add python3 py3-pip python3-dev
}

install_gui_deps_debian() {
    log "Installing GUI dependencies on Debian/Ubuntu..."

    # Detect webkit package
    local webkit_pkg="libwebkit2gtk-4.1-dev"
    if ! apt-cache show "$webkit_pkg" >/dev/null 2>&1; then
        webkit_pkg="libwebkit2gtk-4.0-dev"
    fi

    # Detect appindicator package
    local appind_pkg="libayatana-appindicator3-dev"
    if ! apt-cache show "$appind_pkg" >/dev/null 2>&1; then
        appind_pkg="libappindicator3-dev"
    fi

    maybe_sudo apt-get install -y \
        build-essential \
        curl \
        wget \
        pkg-config \
        libglib2.0-dev \
        libgtk-3-dev \
        "$webkit_pkg" \
        "$appind_pkg" \
        librsvg2-dev \
        lsof

    # Node.js for Tauri frontend
    if ! command_exists npm; then
        log "Installing Node.js..."
        maybe_sudo apt-get install -y nodejs npm
    fi
}

install_gui_deps_fedora() {
    log "Installing GUI dependencies on Fedora/RHEL..."
    maybe_sudo dnf install -y \
        gcc gcc-c++ make \
        curl wget \
        pkg-config \
        glib2-devel \
        gtk3-devel \
        webkit2gtk4.1-devel \
        libappindicator-gtk3-devel \
        librsvg2-devel \
        lsof

    if ! command_exists npm; then
        log "Installing Node.js..."
        maybe_sudo dnf install -y nodejs npm
    fi
}

install_gui_deps_arch() {
    log "Installing GUI dependencies on Arch..."
    maybe_sudo pacman -Sy --noconfirm \
        base-devel \
        curl wget \
        pkgconf \
        glib2 \
        gtk3 \
        webkit2gtk \
        libappindicator-gtk3 \
        librsvg \
        lsof \
        nodejs npm
}

install_gui_deps_suse() {
    log "Installing GUI dependencies on openSUSE..."
    maybe_sudo zypper install -y \
        -t pattern devel_basis \
        curl wget \
        pkg-config \
        glib2-devel \
        gtk3-devel \
        webkit2gtk3-devel \
        libappindicator3-devel \
        librsvg-devel \
        lsof \
        nodejs npm
}

install_rust() {
    if command_exists rustc && command_exists cargo; then
        log "Rust already installed: $(rustc --version)"
        return 0
    fi

    log "Installing Rust via rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path

    # Source cargo env for current session
    if [[ -f "$HOME/.cargo/env" ]]; then
        source "$HOME/.cargo/env"
    fi
}

#------------------------------------------------------------------------------
# Python Environment Setup
#------------------------------------------------------------------------------

setup_python_venv() {
    local venv_dir="$REPO_ROOT/.venv"

    # Find Python 3.12+
    local python_bin=""
    for py in python3.14 python3.13 python3.12 python3; do
        if command_exists "$py"; then
            local ver
            ver="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
            local major minor
            major="${ver%%.*}"
            minor="${ver#*.}"
            if [[ "$major" -ge 3 && "$minor" -ge 12 ]]; then
                python_bin="$py"
                break
            fi
        fi
    done

    if [[ -z "$python_bin" ]]; then
        log_error "Python 3.12+ is required but not found."
        log_error "Install Python 3.12 or newer, then rerun this installer."
        exit 1
    fi

    log "Using Python: $python_bin ($($python_bin --version))"

    if [[ ! -d "$venv_dir" ]]; then
        log "Creating Python virtual environment..."
        "$python_bin" -m venv "$venv_dir"
    fi

    log "Installing Python dependencies..."
    "$venv_dir/bin/python" -m pip install --upgrade pip -q
    "$venv_dir/bin/python" -m pip install -e "$REPO_ROOT[dev]" -q

    log_success "Python environment ready"
}

#------------------------------------------------------------------------------
# Tauri/GUI Setup
#------------------------------------------------------------------------------

setup_tauri() {
    local tauri_dir="$REPO_ROOT/apps/reos-tauri"

    if [[ ! -d "$tauri_dir" ]]; then
        log_warn "Tauri app directory not found at $tauri_dir"
        log_warn "GUI will not be available"
        return 1
    fi

    if ! command_exists npm; then
        log_warn "npm not found. GUI will not be available."
        return 1
    fi

    log "Installing Tauri frontend dependencies..."
    (cd "$tauri_dir" && npm install --silent)

    log_success "Tauri frontend ready"
}

#------------------------------------------------------------------------------
# System Integration
#------------------------------------------------------------------------------

install_cli_symlink() {
    local bin_dir="$INSTALL_PREFIX/bin"
    local symlink="$bin_dir/reos"

    log "Installing CLI to $symlink..."

    # Create bin directory if needed
    if [[ ! -d "$bin_dir" ]]; then
        maybe_sudo mkdir -p "$bin_dir"
    fi

    # Remove old symlink if exists
    if [[ -L "$symlink" || -f "$symlink" ]]; then
        maybe_sudo rm -f "$symlink"
    fi

    # Create symlink
    maybe_sudo ln -sf "$REPO_ROOT/reos" "$symlink"

    log_success "CLI installed: reos"
}

install_desktop_entry() {
    local apps_dir
    if [[ "$USER_INSTALL" == true ]]; then
        apps_dir="$HOME/.local/share/applications"
    else
        apps_dir="/usr/share/applications"
    fi

    local icons_dir
    if [[ "$USER_INSTALL" == true ]]; then
        icons_dir="$HOME/.local/share/icons/hicolor/256x256/apps"
    else
        icons_dir="/usr/share/icons/hicolor/256x256/apps"
    fi

    log "Installing desktop entry..."

    mkdir -p "$apps_dir"
    mkdir -p "$icons_dir"

    # Create desktop entry
    cat > "/tmp/reos.desktop" <<EOF
[Desktop Entry]
Name=ReOS
Comment=Local-first AI companion for Linux
Exec=$REPO_ROOT/reos
Icon=reos
Terminal=false
Type=Application
Categories=Utility;System;
Keywords=ai;assistant;linux;terminal;
StartupNotify=true
StartupWMClass=reos
EOF

    if [[ "$USER_INSTALL" == true ]]; then
        mv "/tmp/reos.desktop" "$apps_dir/reos.desktop"
    else
        maybe_sudo mv "/tmp/reos.desktop" "$apps_dir/reos.desktop"
    fi

    # Copy icon if exists
    local icon_src="$REPO_ROOT/apps/reos-tauri/src-tauri/icons/icon.png"
    if [[ -f "$icon_src" ]]; then
        if [[ "$USER_INSTALL" == true ]]; then
            cp "$icon_src" "$icons_dir/reos.png"
        else
            maybe_sudo cp "$icon_src" "$icons_dir/reos.png"
        fi
    fi

    # Update desktop database
    if command_exists update-desktop-database; then
        if [[ "$USER_INSTALL" == true ]]; then
            update-desktop-database "$apps_dir" 2>/dev/null || true
        else
            maybe_sudo update-desktop-database "$apps_dir" 2>/dev/null || true
        fi
    fi

    log_success "Desktop entry installed"
}

install_shell_integration() {
    log "Setting up shell integration..."

    local shell_name
    shell_name="$(basename "$SHELL")"

    local rc_file=""
    case "$shell_name" in
        bash)
            rc_file="$HOME/.bashrc"
            ;;
        zsh)
            rc_file="$HOME/.zshrc"
            ;;
        *)
            log_warn "Unsupported shell: $shell_name"
            log_warn "Add this to your shell config manually:"
            log_warn "  source \"$REPO_ROOT/scripts/reos-shell-integration.sh\""
            return 0
            ;;
    esac

    # Check if already installed
    if grep -q "reos-shell-integration.sh" "$rc_file" 2>/dev/null; then
        log "Shell integration already configured in $rc_file"
        return 0
    fi

    # Add to shell config
    cat >> "$rc_file" <<EOF

# ReOS Shell Integration
# Type natural language directly in your terminal
if [[ -f "$REPO_ROOT/scripts/reos-shell-integration.sh" ]]; then
    source "$REPO_ROOT/scripts/reos-shell-integration.sh"
fi
EOF

    log_success "Shell integration installed (source $rc_file to activate)"
}

#------------------------------------------------------------------------------
# Uninstall
#------------------------------------------------------------------------------

do_uninstall() {
    log "Uninstalling ReOS..."

    # Remove CLI symlink
    local symlink="$INSTALL_PREFIX/bin/reos"
    if [[ -L "$symlink" ]]; then
        log "Removing CLI symlink..."
        maybe_sudo rm -f "$symlink"
    fi

    # Remove desktop entry
    for apps_dir in "$HOME/.local/share/applications" "/usr/share/applications"; do
        if [[ -f "$apps_dir/reos.desktop" ]]; then
            log "Removing desktop entry from $apps_dir..."
            if [[ "$apps_dir" == "$HOME/.local/share/applications" ]]; then
                rm -f "$apps_dir/reos.desktop"
            else
                maybe_sudo rm -f "$apps_dir/reos.desktop"
            fi
        fi
    done

    # Remove icon
    for icons_dir in "$HOME/.local/share/icons/hicolor/256x256/apps" "/usr/share/icons/hicolor/256x256/apps"; do
        if [[ -f "$icons_dir/reos.png" ]]; then
            log "Removing icon from $icons_dir..."
            if [[ "$icons_dir" == "$HOME/.local"* ]]; then
                rm -f "$icons_dir/reos.png"
            else
                maybe_sudo rm -f "$icons_dir/reos.png"
            fi
        fi
    done

    # Remove shell integration from rc files
    for rc_file in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [[ -f "$rc_file" ]] && grep -q "reos-shell-integration.sh" "$rc_file"; then
            log "Removing shell integration from $rc_file..."
            sed -i '/# ReOS Shell Integration/,/^fi$/d' "$rc_file"
        fi
    done

    log_success "ReOS uninstalled"
    log ""
    log "Note: The ReOS source directory was not removed."
    log "To fully remove: rm -rf $REPO_ROOT"
}

#------------------------------------------------------------------------------
# Main Installation
#------------------------------------------------------------------------------

print_banner() {
    echo -e "${CYAN}"
    cat <<'EOF'
    ____        ____  _____
   / __ \___   / __ \/ ___/
  / /_/ / _ \ / / / /\__ \
 / _, _/  __// /_/ /___/ /
/_/ |_|\___/ \____//____/

Local-first AI companion for Linux
EOF
    echo -e "${NC}"
}

main() {
    print_banner

    if [[ "$UNINSTALL" == true ]]; then
        do_uninstall
        exit 0
    fi

    # Detect distro
    local distro
    distro="$(detect_distro)"
    local distro_family
    distro_family="$(detect_distro_family "$distro")"

    log "Detected: $distro ($distro_family family)"
    log "Install prefix: $INSTALL_PREFIX"
    log "GUI: $INSTALL_GUI | Shell integration: $INSTALL_SHELL"
    echo ""

    # Confirm
    if [[ -t 0 ]]; then
        echo -n "Proceed with installation? [Y/n] "
        read -r response
        case "$response" in
            n|N|no|NO)
                log "Installation cancelled."
                exit 0
                ;;
        esac
    fi

    echo ""

    #--------------------------------------------------------------------------
    # Step 1: Install system dependencies
    #--------------------------------------------------------------------------
    log "${BOLD}Step 1/5: Installing system dependencies...${NC}"

    case "$distro_family" in
        debian)
            install_python_debian
            [[ "$INSTALL_GUI" == true ]] && install_gui_deps_debian
            ;;
        fedora)
            install_python_fedora
            [[ "$INSTALL_GUI" == true ]] && install_gui_deps_fedora
            ;;
        arch)
            install_python_arch
            [[ "$INSTALL_GUI" == true ]] && install_gui_deps_arch
            ;;
        suse)
            install_python_suse
            [[ "$INSTALL_GUI" == true ]] && install_gui_deps_suse
            ;;
        alpine)
            install_python_alpine
            log_warn "Alpine GUI support is limited"
            ;;
        nix)
            log "NixOS detected. Assuming dependencies are in your configuration."
            ;;
        *)
            log_warn "Unknown distro. Attempting to continue..."
            log_warn "You may need to install dependencies manually:"
            log_warn "  - Python 3.12+"
            log_warn "  - Node.js + npm (for GUI)"
            log_warn "  - Rust + Cargo (for GUI)"
            log_warn "  - GTK3 + WebKit2GTK dev packages (for GUI)"
            ;;
    esac

    #--------------------------------------------------------------------------
    # Step 2: Install Rust (for GUI)
    #--------------------------------------------------------------------------
    if [[ "$INSTALL_GUI" == true ]]; then
        log "${BOLD}Step 2/5: Setting up Rust...${NC}"
        install_rust
    else
        log "${BOLD}Step 2/5: Skipping Rust (--no-gui)${NC}"
    fi

    #--------------------------------------------------------------------------
    # Step 3: Setup Python environment
    #--------------------------------------------------------------------------
    log "${BOLD}Step 3/5: Setting up Python environment...${NC}"
    setup_python_venv

    #--------------------------------------------------------------------------
    # Step 4: Setup Tauri frontend
    #--------------------------------------------------------------------------
    if [[ "$INSTALL_GUI" == true ]]; then
        log "${BOLD}Step 4/5: Setting up Tauri frontend...${NC}"
        setup_tauri || log_warn "Tauri setup failed. GUI may not work."
    else
        log "${BOLD}Step 4/5: Skipping Tauri (--no-gui)${NC}"
    fi

    #--------------------------------------------------------------------------
    # Step 5: System integration
    #--------------------------------------------------------------------------
    log "${BOLD}Step 5/5: System integration...${NC}"

    install_cli_symlink

    if [[ "$INSTALL_GUI" == true ]]; then
        install_desktop_entry
    fi

    if [[ "$INSTALL_SHELL" == true ]]; then
        install_shell_integration
    fi

    #--------------------------------------------------------------------------
    # Done!
    #--------------------------------------------------------------------------
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}${BOLD}  ReOS installed successfully!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  ${BOLD}Quick Start:${NC}"
    echo ""
    echo -e "    ${CYAN}reos${NC}                    Launch the GUI"
    echo -e "    ${CYAN}reos --service${NC}          Start the API server"
    echo -e "    ${CYAN}reos -p \"query\"${NC}         Run a single prompt"
    echo ""

    if [[ "$INSTALL_SHELL" == true ]]; then
        echo -e "  ${BOLD}Shell Integration:${NC}"
        echo ""
        echo -e "    ${DIM}# Activate in current shell:${NC}"
        echo -e "    ${CYAN}source ~/.bashrc${NC}  ${DIM}# or ~/.zshrc${NC}"
        echo ""
        echo -e "    ${DIM}# Then just type natural language:${NC}"
        echo -e "    ${CYAN}what files are in my home directory${NC}"
        echo ""
    fi

    echo -e "  ${BOLD}Documentation:${NC}"
    echo -e "    https://github.com/yourorg/reos"
    echo ""
    echo -e "  ${BOLD}Uninstall:${NC}"
    echo -e "    ${CYAN}./install.sh --uninstall${NC}"
    echo ""
}

main "$@"
