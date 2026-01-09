# Script to create a fresh main branch without history
# This removes all Git history including the secret

Write-Host "========================================" -ForegroundColor Yellow
Write-Host "Creating Fresh Main Branch" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "WARNING: This will DELETE all commit history!" -ForegroundColor Red
Write-Host "Make sure you have a backup of your code." -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Are you sure you want to proceed? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit
}

Write-Host ""
Write-Host "Step 1: Checking current status..." -ForegroundColor Green
git status

Write-Host ""
Write-Host "Step 2: Stashing any uncommitted changes..." -ForegroundColor Green
git stash push -m "Stashed before creating fresh main branch"

Write-Host ""
Write-Host "Step 3: Creating backup of current main branch..." -ForegroundColor Green
git branch backup-old-main-with-history 2>&1 | Out-Null
Write-Host "Backup created: backup-old-main-with-history" -ForegroundColor Green

Write-Host ""
Write-Host "Step 4: Creating new orphan branch (no history)..." -ForegroundColor Green
git checkout --orphan fresh-main

Write-Host ""
Write-Host "Step 5: Removing all files from staging area..." -ForegroundColor Green
git rm -rf --cached . 2>&1 | Out-Null

Write-Host ""
Write-Host "Step 6: Adding all current files..." -ForegroundColor Green
git add .

Write-Host ""
Write-Host "Step 7: Creating initial commit..." -ForegroundColor Green
git commit -m "Initial commit - fresh start without history"

Write-Host ""
Write-Host "Step 8: Deleting old main branch..." -ForegroundColor Yellow
git branch -D main

Write-Host ""
Write-Host "Step 9: Renaming fresh-main to main..." -ForegroundColor Green
git branch -m main

Write-Host ""
Write-Host "Step 10: Verifying secret is not in new history..." -ForegroundColor Green
$found = git log --all -p | Select-String "2/ISQ"
if ($found) {
    Write-Host "WARNING: Secret still found!" -ForegroundColor Red
} else {
    Write-Host "Secret not found in new history!" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Review your files: git status" -ForegroundColor White
Write-Host "2. Delete old branches on remote (if needed):" -ForegroundColor White
Write-Host "   git push origin --delete backup-before-github-fix" -ForegroundColor Cyan
Write-Host "   git push origin --delete backup-before-github-fix-2" -ForegroundColor Cyan
Write-Host "   git push origin --delete backup-before-secret-removal" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Force push new main branch:" -ForegroundColor White
Write-Host "   git push --force origin main" -ForegroundColor Cyan
Write-Host ""
Write-Host "4. Set main as default branch on GitHub (if needed)" -ForegroundColor White
Write-Host ""
Write-Host "5. Rotate Azure Storage Account key in Azure Portal" -ForegroundColor Red
Write-Host ""
Write-Host "WARNING: Force push will overwrite remote history!" -ForegroundColor Red
Write-Host "Make sure you coordinate with your team." -ForegroundColor Yellow
Write-Host ""
Write-Host "Your old main branch is backed up locally as: backup-old-main-with-history" -ForegroundColor Cyan

