# Script to create a fresh prod branch without history
# This removes all Git history including the secret

Write-Host "========================================" -ForegroundColor Yellow
Write-Host "Creating Fresh Prod Branch" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "WARNING: This will create a new branch with NO commit history!" -ForegroundColor Red
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
git stash push -m "Stashed before creating fresh prod branch"

Write-Host ""
Write-Host "Step 3: Creating backup of current branch..." -ForegroundColor Green
$currentBranch = git branch --show-current
git branch backup-old-$currentBranch-with-history 2>&1 | Out-Null
Write-Host "Backup created: backup-old-$currentBranch-with-history" -ForegroundColor Green

Write-Host ""
Write-Host "Step 4: Checking if prod branch already exists..." -ForegroundColor Green
$prodExists = git branch --list prod
if ($prodExists) {
    Write-Host "WARNING: prod branch already exists!" -ForegroundColor Yellow
    $deleteProd = Read-Host "Delete existing prod branch? (yes/no)"
    if ($deleteProd -eq "yes") {
        git branch -D prod
        Write-Host "Old prod branch deleted." -ForegroundColor Green
    } else {
        Write-Host "Cancelled. Please delete or rename the existing prod branch first." -ForegroundColor Red
        exit
    }
}

Write-Host ""
Write-Host "Step 5: Creating new orphan branch (no history)..." -ForegroundColor Green
git checkout --orphan prod

Write-Host ""
Write-Host "Step 6: Removing all files from staging area..." -ForegroundColor Green
git rm -rf --cached . 2>&1 | Out-Null

Write-Host ""
Write-Host "Step 7: Adding all current files..." -ForegroundColor Green
git add .

Write-Host ""
Write-Host "Step 8: Creating initial commit..." -ForegroundColor Green
git commit -m "Initial commit - fresh prod branch without history"

Write-Host ""
Write-Host "Step 9: Verifying secret is not in new history..." -ForegroundColor Green
$found = git log --all -p | Select-String "2/ISQ"
if ($found) {
    Write-Host "WARNING: Secret still found!" -ForegroundColor Red
} else {
    Write-Host "Secret not found in new prod branch history!" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Review your files: git status" -ForegroundColor White
Write-Host "2. Verify you're on prod branch: git branch" -ForegroundColor White
Write-Host ""
Write-Host "3. Delete old branches on remote (if needed):" -ForegroundColor White
Write-Host "   git push origin --delete backup-before-github-fix" -ForegroundColor Cyan
Write-Host "   git push origin --delete backup-before-github-fix-2" -ForegroundColor Cyan
Write-Host "   git push origin --delete backup-before-secret-removal" -ForegroundColor Cyan
Write-Host ""
Write-Host "4. Push new prod branch to remote:" -ForegroundColor White
Write-Host "   git push -u origin prod" -ForegroundColor Cyan
Write-Host ""
Write-Host "   If prod branch exists on remote and you want to replace it:" -ForegroundColor Yellow
Write-Host "   git push --force origin prod" -ForegroundColor Cyan
Write-Host ""
Write-Host "5. (Optional) Set prod as default branch on GitHub" -ForegroundColor White
Write-Host ""
Write-Host "6. Rotate Azure Storage Account key in Azure Portal" -ForegroundColor Red
Write-Host ""
Write-Host "WARNING: Force push will overwrite remote history!" -ForegroundColor Red
Write-Host "Make sure you coordinate with your team." -ForegroundColor Yellow
Write-Host ""
Write-Host "Your old branch is backed up locally as: backup-old-$currentBranch-with-history" -ForegroundColor Cyan
Write-Host "You are now on the fresh 'prod' branch with no history." -ForegroundColor Green

