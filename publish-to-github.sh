#!/usr/bin/env bash
# Upload this complete project (source + assets + video) to your GitHub repository.
set -euo pipefail
cd "$(dirname "$0")"
REPO="https://github.com/anhads3ngh/MatchPulse-Game-QA.git"
if ! command -v git >/dev/null 2>&1; then
  echo 'Git is required. Install Git from https://git-scm.com/ and run again.'
  exit 1
fi
if [ ! -d .git ]; then
  git init
fi
git branch -M main
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO"
else
  git remote add origin "$REPO"
fi
git add -A
if ! git diff --cached --quiet; then
  git -c user.name='Anhad Singh Sarna' -c user.email='159742010+anhads3ngh@users.noreply.github.com' commit -m 'Launch MatchPulse game quality intelligence platform with demo video'
fi
printf '\nPushing entire repository to %s\n' "$REPO"
git push --set-upstream origin main
printf '\nSUCCESS: https://github.com/anhads3ngh/MatchPulse-Game-QA\n'
