#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${1:-$HOME/Telegram-iOS-Ghost/repo}"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "❌ Git repo not found: $REPO_DIR"
  exit 1
fi

cd "$REPO_DIR"
mkdir -p payload .github/workflows
cp "$SRC/apply_ayu_v02.py" ./apply_ayu_v02.py
cp "$SRC/payload/AyuRuntimeSettings.swift" ./payload/AyuRuntimeSettings.swift
cp "$SRC/.github/workflows/build-ipa.yml" ./.github/workflows/build-ipa.yml
cp "$SRC/.github/workflows/verify-patch.yml" ./.github/workflows/verify-patch.yml
chmod +x apply_ayu_v02.py

# Pin Telegram to the exact current master commit so patch anchors and the Bazel cache stay stable.
gh api repos/TelegramMessenger/Telegram-iOS/commits/master --jq '.sha' > telegram-ref.txt

git rm -f apply_ghost_mode.py 2>/dev/null || true
git rm -f payload/GhostModeSettings.swift 2>/dev/null || true
python3 -m py_compile apply_ayu_v02.py

git add apply_ayu_v02.py payload/AyuRuntimeSettings.swift telegram-ref.txt .github/workflows/build-ipa.yml .github/workflows/verify-patch.yml
git commit -m "Ayu iOS v0.2 stable Ghost + persistent Bazel cache" || true
git push origin main

OWNER_REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"
SHA="$(git rev-parse HEAD)"
echo "✅ pushed $SHA to $OWNER_REPO"

echo "▶ Verify patch first (cheap)"
gh workflow run verify-patch.yml --repo "$OWNER_REPO" --ref main
sleep 4
VERIFY_ID="$(gh run list --repo "$OWNER_REPO" --workflow verify-patch.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
echo "Verify Run ID: $VERIFY_ID"
gh run watch "$VERIFY_ID" --repo "$OWNER_REPO" --compact

VERIFY_RESULT="$(gh run view "$VERIFY_ID" --repo "$OWNER_REPO" --json conclusion --jq '.conclusion')"
if [ "$VERIFY_RESULT" != "success" ]; then
  echo "❌ Verify failed. Full one-hour build was NOT started."
  exit 1
fi

echo "✅ verify passed; starting IPA build"
gh workflow run build-ipa.yml --repo "$OWNER_REPO" --ref main
sleep 4
BUILD_ID="$(gh run list --repo "$OWNER_REPO" --workflow build-ipa.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
echo "Build Run ID: $BUILD_ID"
echo "Watch: gh run watch $BUILD_ID --repo '$OWNER_REPO' --compact"
echo "After success: gh run download $BUILD_ID --repo '$OWNER_REPO' -n AyuGram-iOS-v0.2-IPA -D ~/storage/downloads/AyuGram-v02"
