@echo off
setlocal
cd /d "%~dp0"
set REPO=https://github.com/anhads3ngh/MatchPulse-Game-QA.git
where git >nul 2>nul || (echo Git not found. Install from https://git-scm.com/ & exit /b 1)
if not exist .git git init
git branch -M main
git remote get-url origin >nul 2>nul
if errorlevel 1 (git remote add origin %REPO%) else (git remote set-url origin %REPO%)
git add -A
git diff --cached --quiet
if errorlevel 1 git -c user.name="Anhad Singh Sarna" -c user.email="159742010+anhads3ngh@users.noreply.github.com" commit -m "Launch MatchPulse with demo video"
git push --set-upstream origin main
if errorlevel 1 (echo Push failed. See error above. & exit /b 1)
echo SUCCESS: https://github.com/anhads3ngh/MatchPulse-Game-QA
pause
