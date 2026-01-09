#!/bin/bash
# Simple script to remove Azure Storage Account Key from git history
# This uses git filter-repo (recommended) or git filter-branch

echo "========================================"
echo "Removing Azure Storage Account Key from git history"
echo "========================================"
echo ""
echo "WARNING: This will rewrite git history!"
echo "Make sure you have a backup of your repository."
echo ""

# Check if git-filter-repo is installed
if command -v git-filter-repo &> /dev/null; then
    echo "Using git-filter-repo (recommended method)..."
    
    # Create backup branch
    git branch backup-before-secret-removal
    
    # Remove the secret using git-filter-repo
    git filter-repo --path src/config.py --invert-paths
    git filter-repo --path src/config.py --use-base-name
    
    # Replace secret in the file
    git filter-repo --replace-text <(echo "AccountKey=2/ISQ/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu/d6UA====>AccountKey=[REMOVED_SECRET]")
    
else
    echo "Using git filter-branch (fallback method)..."
    
    # Create backup branch
    git branch backup-before-secret-removal
    
    # Remove secret from all commits
    git filter-branch --force --index-filter \
        'git checkout HEAD -- src/config.py 2>/dev/null || true' \
        --prune-empty --tag-name-filter cat -- --all
    
    # Replace the secret string in all commits
    git filter-branch --force --tree-filter \
        'if [ -f src/config.py ]; then sed -i "s/AccountKey=2\/ISQ\/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu\/d6UA==/AccountKey=[REMOVED_SECRET]/g" src/config.py; fi' \
        --prune-empty --tag-name-filter cat -- --all
    
    # Clean up
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
fi

echo ""
echo "========================================"
echo "Done! Secret removed from git history."
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Review: git log --all"
echo "2. Verify: git log -p --all | grep '2/ISQ'"
echo "3. Force push: git push --force --all"
echo ""

