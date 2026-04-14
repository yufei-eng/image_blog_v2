#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Image Blog & Life Comic Skills — Auto Updater
#  Pulls latest from GitHub and verifies dependencies
# ============================================================

REPO_DIR="$HOME/.local/share/image_blog"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo ""
echo "========================================"
echo "  Image Blog & Life Comic Updater"
echo "========================================"
echo ""

if [ ! -d "$REPO_DIR/.git" ]; then
    err "Not installed. Run install.sh first: bash <(curl -s https://raw.githubusercontent.com/yufei-eng/image_blog/main/install.sh)"
fi

cd "$REPO_DIR"

BEFORE=$(git rev-parse HEAD)
info "Current version: $(git log -1 --format='%h %s')"

info "Pulling latest changes..."
git pull --ff-only origin main

AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
    info "Already up to date!"
else
    CHANGES=$(git log --oneline "$BEFORE..$AFTER" | wc -l | tr -d ' ')
    info "Updated! $CHANGES new commit(s):"
    git log --oneline "$BEFORE..$AFTER" | head -10
    echo ""

    info "Checking Python dependencies..."
    pip3 install --quiet --upgrade google-genai Pillow 2>/dev/null || \
    pip install --quiet --upgrade google-genai Pillow 2>/dev/null || \
    warn "Could not auto-update deps. Run: pip install google-genai Pillow"
fi

info "Verifying symlinks..."
for platform_dir in "$HOME/.claude/skills" "$HOME/.cursor/skills"; do
    for skill in photo-blog life-comic; do
        link="$platform_dir/$skill"
        if [ -L "$link" ]; then
            info "  $link -> $(readlink "$link")"
        elif [ -d "$platform_dir" ]; then
            warn "  $link missing — re-run install.sh to fix"
        fi
    done
done

echo ""
info "Now at: $(git log -1 --format='%h %s')"
echo "========================================"
