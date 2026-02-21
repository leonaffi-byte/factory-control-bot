#!/bin/bash
set -e
PROJECT_NAME="$1"
DESCRIPTION="$2"
source ~/.factory-env

if [ -z "$PROJECT_NAME" ]; then
    echo "Usage: ~/new-project.sh <project-name> \"Short description\""
    exit 1
fi
if [ -d "$HOME/projects/$PROJECT_NAME" ]; then
    echo "ERROR: Project $PROJECT_NAME already exists"
    exit 1
fi

echo "=== Creating: $PROJECT_NAME ==="
cp -r ~/factory-template ~/projects/$PROJECT_NAME
cd ~/projects/$PROJECT_NAME
rm -rf .git
git init && git add -A && git commit -m "Initial factory template"

echo "=== Creating GitHub repo ==="
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" https://api.github.com/user/repos \
    -d "{\"name\":\"$PROJECT_NAME\",\"private\":true,\"description\":\"$DESCRIPTION\"}")

if [ "$HTTP_CODE" != "201" ]; then
    echo "WARNING: GitHub returned HTTP $HTTP_CODE (repo may already exist)"
fi
sleep 5

git remote add origin git@github.com:$GITHUB_USER/$PROJECT_NAME.git 2>/dev/null || \
    git remote set-url origin git@github.com:$GITHUB_USER/$PROJECT_NAME.git
git push -u origin main
git checkout -b dev
git push -u origin dev

mkdir -p artifacts/requirements artifacts/reports
[ -n "$DESCRIPTION" ] && echo "$DESCRIPTION" > artifacts/requirements/raw-input.md || \
    echo "Describe your project here, then run /factory" > artifacts/requirements/raw-input.md

cat > artifacts/reports/audit-log.md << AEOF
# Factory Audit Log
## Project Created
- Date: $(date +%Y-%m-%d)
- Project: $PROJECT_NAME
AEOF

git add -A && git commit -m "Add requirements and audit log" && git push

echo ""
echo "=== Done! ==="
echo "  Edit: nano ~/projects/$PROJECT_NAME/artifacts/requirements/raw-input.md"
echo "  Run:  fsg $PROJECT_NAME  (Gemini) or fsc $PROJECT_NAME  (Claude)"
