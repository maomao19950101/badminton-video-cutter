#!/usr/bin/env bash
# 🏸 Badminton Video Cutter - One-Click Git Commit, Tag & Push Script

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

MSG="${1:-update: sync skill improvements}"
TAG="${2:-}"

echo "🏸 [Badminton Video Cutter] Preparing Git Push..."
git status

git add -A

if git diff-index --quiet HEAD --; then
    echo "ℹ️ No uncommitted changes."
else
    git commit -m "$MSG"
    echo "✅ Changes committed: $MSG"
fi

if [ -n "$TAG" ]; then
    echo "🏷️ Tagging version: $TAG"
    git tag -fa "$TAG" -m "Release $TAG"
fi

echo "🚀 Pushing to GitHub (git@github.com:maomao19950101/badminton-video-cutter.git)..."
git push -u origin main --tags

echo "🎉 Successfully pushed to GitHub!"
