#!/bin/bash
# Helper: commit local changes and push to GitHub (origin) + Heroku.
set -e

MSG="${1:-chore: update}"

git add .
git commit -m "$MSG" || echo "No changes to commit."
git push origin HEAD

if git remote get-url heroku > /dev/null 2>&1; then
  git push heroku main
else
  echo "Heroku remote not configured — skipping (heroku git:remote -a APP_NAME)."
fi
