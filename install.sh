#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Image Blog & Life Comic Skills — One-Click Installer
#  Supports: Claude Code (~/.claude/skills/) and Cursor (~/.cursor/skills/)
# ============================================================

REPO_URL="https://github.com/yufei-eng/image_blog.git"
REPO_DIR="$HOME/.local/share/image_blog"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }

echo ""
echo "========================================"
echo "  Image Blog & Life Comic Installer"
echo "  v0.2"
echo "========================================"
echo ""

# --- 1. Clone or update repo ---
if [ -d "$REPO_DIR/.git" ]; then
    info "Repo already exists at $REPO_DIR, pulling latest..."
    cd "$REPO_DIR" && git pull --ff-only origin main
else
    info "Cloning repo to $REPO_DIR..."
    git clone "$REPO_URL" "$REPO_DIR"
fi

# --- 2. Install Python dependencies ---
info "Installing Python dependencies..."
pip3 install --quiet --upgrade google-genai Pillow 2>/dev/null || \
pip install --quiet --upgrade google-genai Pillow 2>/dev/null || \
warn "Could not auto-install deps. Run manually: pip install google-genai Pillow"

# --- 3. Create symlinks for Claude Code ---
CLAUDE_SKILLS="$HOME/.claude/skills"
if [ -d "$HOME/.claude" ]; then
    mkdir -p "$CLAUDE_SKILLS"

    for skill in photo-blog life-comic; do
        target="$CLAUDE_SKILLS/$skill"
        source="$REPO_DIR/skills/$skill"
        if [ -L "$target" ]; then
            rm "$target"
        elif [ -d "$target" ]; then
            warn "$target already exists as directory, backing up to ${target}.bak"
            mv "$target" "${target}.bak.$(date +%s)"
        fi
        ln -s "$source" "$target"
        info "Claude Code: $target -> $source"
    done
else
    warn "~/.claude not found, skipping Claude Code symlinks"
fi

# --- 4. Create symlinks for Cursor ---
CURSOR_SKILLS="$HOME/.cursor/skills"
mkdir -p "$CURSOR_SKILLS"

for skill in photo-blog life-comic; do
    target="$CURSOR_SKILLS/$skill"
    source="$REPO_DIR/skills/$skill"
    if [ -L "$target" ]; then
        rm "$target"
    elif [ -d "$target" ]; then
        warn "$target already exists as directory, backing up to ${target}.bak"
        mv "$target" "${target}.bak.$(date +%s)"
    fi
    ln -s "$source" "$target"
    info "Cursor: $target -> $source"
done

# --- 5. Setup config ---
for skill in photo-blog life-comic; do
    config="$REPO_DIR/skills/$skill/config.json"
    example="$REPO_DIR/skills/$skill/config.json.example"
    if [ ! -f "$config" ] && [ -f "$example" ]; then
        cp "$example" "$config"
        warn "Created $config from template — edit it to add your API token"
    fi
done

echo ""
echo "========================================"
info "Installation complete!"
echo ""
echo "  Next steps:"
echo "  1. Edit config.json with your API token:"
echo "     $REPO_DIR/skills/photo-blog/config.json"
echo "     $REPO_DIR/skills/life-comic/config.json"
echo ""
echo "  2. Use in Claude Code / Cursor:"
echo "     'Generate a photo blog from my photos'"
echo "     'Turn my photos into a comic'"
echo ""
echo "  3. To update later, run:"
echo "     bash $REPO_DIR/update.sh"
echo "========================================"
