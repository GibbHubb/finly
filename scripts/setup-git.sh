#!/usr/bin/env bash
# Run this once after cloning to set up the branch structure
set -e

echo "Setting up Finly git workflow..."

git checkout -b main 2>/dev/null || git checkout main
git checkout -b develop 2>/dev/null || echo "develop already exists"

if git remote get-url origin &>/dev/null; then
  git push -u origin main
  git push -u origin develop
fi

echo "Git setup complete!"
echo ""
echo "Daily workflow:"
echo "  git checkout develop"
echo "  git checkout -b feature/my-feature"
echo "  git add -p                           # stage hunks interactively"
echo "  git commit -m 'feat(scope): message'"
echo "  git push -u origin feature/my-feature"
echo "  # open PR into develop on GitHub"
