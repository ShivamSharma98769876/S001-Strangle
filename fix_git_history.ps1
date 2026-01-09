# Simple script to fix git history - removes Azure Storage Account key
# Run this script in PowerShell

Write-Host "========================================" -ForegroundColor Yellow
Write-Host "Fixing Git History - Removing Secret" -ForegroundColor Yellow  
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

# Check if we're in a git repo
if (-not (Test-Path .git)) {
    Write-Host "Error: Not in a git repository!" -ForegroundColor Red
    exit 1
}

Write-Host "Step 1: Creating backup branch..." -ForegroundColor Green
git branch backup-before-secret-removal 2>&1 | Out-Null
Write-Host "✓ Backup created: backup-before-secret-removal" -ForegroundColor Green
Write-Host ""

Write-Host "Step 2: Checking for BFG Repo-Cleaner..." -ForegroundColor Green
$bfgPath = Get-Command bfg -ErrorAction SilentlyContinue
if ($bfgPath) {
    Write-Host "✓ BFG found - using BFG (recommended)" -ForegroundColor Green
    Write-Host ""
    
    # Create secrets file
    $secretsFile = "secrets-to-remove.txt"
    "AccountKey=2/ISQ/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu/d6UA==" | Out-File $secretsFile
    
    Write-Host "Running BFG to remove secret..." -ForegroundColor Yellow
    bfg --replace-text $secretsFile
    Remove-Item $secretsFile
    
    Write-Host ""
    Write-Host "Cleaning up..." -ForegroundColor Green
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
    
} else {
    Write-Host "BFG not found. Using git filter-branch..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "WARNING: This method is slower and may have issues on Windows." -ForegroundColor Red
    Write-Host "Consider installing BFG: https://rtyley.github.io/bfg-repo-cleaner/" -ForegroundColor Yellow
    Write-Host ""
    
    $confirm = Read-Host "Continue with filter-branch? (yes/no)"
    if ($confirm -ne "yes") {
        Write-Host "Aborted. Install BFG for a better experience." -ForegroundColor Yellow
        exit
    }
    
    Write-Host ""
    Write-Host "Removing secret from all commits..." -ForegroundColor Yellow
    Write-Host "This may take several minutes..." -ForegroundColor Yellow
    
    # Create a bash script for git filter-branch (works better than PowerShell)
    $bashScript = @'
#!/bin/bash
if [ -f src/config.py ]; then
    sed -i 's|AccountKey=2/ISQ/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu/d6UA==|AccountKey=[REMOVED_SECRET]|g' src/config.py
fi
'@
    
    $bashScript | Out-File -Encoding ASCII "filter-script.sh"
    
    # Try to use git bash or WSL
    if (Get-Command bash -ErrorAction SilentlyContinue) {
        Write-Host "Using bash for filter-branch..." -ForegroundColor Green
        bash -c "git filter-branch --force --tree-filter 'bash filter-script.sh' --prune-empty --tag-name-filter cat -- --all"
    } else {
        Write-Host "Error: bash not found. Please install Git Bash or use BFG." -ForegroundColor Red
        Write-Host "Download BFG: https://rtyley.github.io/bfg-repo-cleaner/" -ForegroundColor Yellow
        Remove-Item "filter-script.sh" -ErrorAction SilentlyContinue
        exit 1
    }
    
    Remove-Item "filter-script.sh" -ErrorAction SilentlyContinue
    
    Write-Host ""
    Write-Host "Cleaning up..." -ForegroundColor Green
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Done! Verifying..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Verify
$found = git log -p --all | Select-String "2/ISQ"
if ($found) {
    Write-Host "WARNING: Secret still found in history!" -ForegroundColor Red
    Write-Host "You may need to use BFG Repo-Cleaner instead." -ForegroundColor Yellow
} else {
    Write-Host "✓ Secret successfully removed from git history!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Review: git log --all" -ForegroundColor White
Write-Host "2. Force push: git push --force --all" -ForegroundColor White
Write-Host "   (WARNING: This overwrites remote history!)" -ForegroundColor Red
Write-Host ""
Write-Host "IMPORTANT: Rotate the Azure Storage Account key in Azure Portal!" -ForegroundColor Red
Write-Host "The exposed key should be considered compromised." -ForegroundColor Red

