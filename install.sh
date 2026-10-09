#!/usr/bin/env bash
# ==============================================================================
# GoGuard Telegram Bot - 1-Click Interactive VPS Installer
# ==============================================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}        🚀 GoGuard Telegram Bot - Linux VPS Installer             ${NC}"
echo -e "${CYAN}==================================================================${NC}"

# Check root privileges
if [ "$EUID" -ne 0 ]; then
  echo -e "${YELLOW}Warning: Running without root privileges. Some package installations may fail.${NC}"
fi

# Locate or clone project directory
INSTALL_DIR="$HOME/goguard-telegram-bot"
REPO_URL="https://github.com/armanpier/goguard-telegram-bot.git"

if [ ! -f "setup.py" ]; then
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}ℹ️ Existing installation found at $INSTALL_DIR. Navigating...${NC}"
        cd "$INSTALL_DIR"
    else
        echo -e "${CYAN}📥 Cloning GoGuard Telegram Bot into $INSTALL_DIR...${NC}"
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
fi

# Pull latest commits if inside git worktree
if [ -d ".git" ]; then
    echo -e "${CYAN}🔄 Syncing latest updates from GitHub...${NC}"
    git stash >/dev/null 2>&1 || true
    git pull origin main || true
fi

# Detect package manager and install requirements
echo -e "\n${CYAN}[1/4] Checking system dependencies (Python 3.11+, Git, Curl)...${NC}"
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv git curl
elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 python3-pip git curl
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 python3-pip git curl
fi

# Set up virtual environment if not already present
echo -e "\n${CYAN}[2/4] Setting up Python virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

echo -e "\n${CYAN}[3/4] Installing Python requirements and preparing data directory...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# Ensure data directory exists with full write permissions for SQLite
mkdir -p data
chmod -R 777 data

# Run interactive configuration wizard
echo -e "\n${CYAN}[4/4] Launching Interactive Setup Wizard...${NC}"
python3 setup.py

echo -e "\n${GREEN}Installation script finished!${NC}"
