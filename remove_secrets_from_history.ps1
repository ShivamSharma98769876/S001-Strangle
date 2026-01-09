# Script to remove Azure Storage Account Key from git history
# This will rewrite git history - USE WITH CAUTION
# Run this script to remove the secret from all commits

Write-Host "========================================" -ForegroundColor Yellow
Write-Host "Removing Azure Storage Account Key from git history" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "WARNING: This will rewrite git history!" -ForegroundColor Red
Write-Host "Make sure you have a backup of your repository." -ForegroundColor Red
Write-Host ""
Write-Host "The secret to remove:" -ForegroundColor Cyan
Write-Host "AccountKey=2/ISQ/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu/d6UA==" -ForegroundColor Cyan
Write-Host ""

$confirm = Read-Host "Do you want to proceed? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit
}

Write-Host ""
Write-Host "Step 1: Creating backup branch..." -ForegroundColor Green
git branch backup-before-secret-removal

Write-Host ""
Write-Host "Step 2: Removing secret from git history using filter-branch..." -ForegroundColor Green
Write-Host "This may take a few minutes..." -ForegroundColor Yellow

# Escape special characters for PowerShell regex
$secretPattern = [regex]::Escape('AccountKey=2/ISQ/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu/d6UA==')
$replacement = 'AccountKey=[REMOVED_SECRET]'

# Create a temporary script file for git filter-branch
$tempScript = [System.IO.Path]::GetTempFileName()
$scriptContent = @"
if [ -f src/config.py ]; then
    sed -i 's/AccountKey=2\/ISQ\/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu\/d6UA==/AccountKey=[REMOVED_SECRET]/g' src/config.py
fi
"@

# For Windows, we need a different approach
# Use git filter-branch with a PowerShell command
Write-Host "Replacing secret in all commits..." -ForegroundColor Yellow

# Use git filter-branch with tree-filter
# Note: This requires bash or WSL on Windows, or we use a different approach
git filter-branch --force --tree-filter "powershell -Command `"if (Test-Path src/config.py) { `$content = Get-Content src/config.py -Raw; `$content = `$content -replace '$secretPattern', '$replacement'; [System.IO.File]::WriteAllText((Resolve-Path src/config.py), `$content) }`"" --prune-empty --tag-name-filter cat -- --all

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Error: git filter-branch failed. Trying alternative method..." -ForegroundColor Red
    Write-Host ""
    Write-Host "Alternative: Use BFG Repo-Cleaner or manual rebase (see REMOVE_SECRETS_MANUAL.md)" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Step 3: Cleaning up..." -ForegroundColor Green
git reflog expire --expire=now --all
git gc --prune=now --aggressive

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Done! Secret removed from git history." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Review the changes: git log --all" -ForegroundColor White
Write-Host "2. Verify secret is gone: git log -p --all | Select-String '2/ISQ'" -ForegroundColor White
Write-Host "   (Should return nothing if successful)" -ForegroundColor Gray
Write-Host "3. Force push to remote: git push --force --all" -ForegroundColor White
Write-Host "   (WARNING: This will overwrite remote history!)" -ForegroundColor Red
Write-Host ""
Write-Host "If something goes wrong, restore from backup:" -ForegroundColor Yellow
Write-Host "  git reset --hard backup-before-secret-removal" -ForegroundColor White
Write-Host ""
Write-Host "IMPORTANT: Rotate the Azure Storage Account key in Azure Portal!" -ForegroundColor Red
Write-Host "The key was exposed in git history and should be considered compromised." -ForegroundColor Red

