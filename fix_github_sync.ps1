# Script to fix GitHub sync error by removing secret from all history
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "Fixing GitHub Sync Error" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

# Check if BFG is available
$bfgPath = Get-Command bfg -ErrorAction SilentlyContinue
$bfgJar = $null
$bfgCommand = "bfg"

if ($bfgPath) {
    Write-Host "BFG found in PATH - using BFG (recommended)" -ForegroundColor Green
    $useFilterBranch = "no"
} else {
    # Try to find BFG JAR file in common locations
    $possibleJarPaths = @(
        "$env:USERPROFILE\Downloads\bfg*.jar",
        "$env:USERPROFILE\Desktop\bfg*.jar",
        "C:\Tools\bfg*.jar",
        ".\bfg*.jar"
    )
    
    foreach ($pattern in $possibleJarPaths) {
        $found = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $bfgJar = $found.FullName
            $bfgCommand = "java -jar `"$bfgJar`""
            Write-Host "BFG JAR found at: $bfgJar" -ForegroundColor Green
            Write-Host "Using BFG (recommended)" -ForegroundColor Green
            $useFilterBranch = "no"
            break
        }
    }
    
    if (-not $bfgJar) {
        Write-Host "BFG Repo-Cleaner not found." -ForegroundColor Red
        Write-Host ""
        Write-Host "Please download BFG from: https://rtyley.github.io/bfg-repo-cleaner/" -ForegroundColor Yellow
        Write-Host "Then run this script again." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Alternative: Use git filter-branch (slower, less reliable)" -ForegroundColor Cyan
        $useFilterBranch = Read-Host "Use git filter-branch instead? (yes/no)"
        if ($useFilterBranch -ne "yes") {
            exit
        }
    }
}

# Create backup
Write-Host ""
Write-Host "Step 1: Creating backup branch..." -ForegroundColor Green
git branch backup-before-github-fix 2>&1 | Out-Null
Write-Host "Backup created" -ForegroundColor Green

if ($useFilterBranch -eq "yes") {
    Write-Host ""
    Write-Host "Step 2: Using git filter-branch to remove secret..." -ForegroundColor Yellow
    Write-Host "This will take several minutes..." -ForegroundColor Yellow
    
    $env:FILTER_BRANCH_SQUELCH_WARNING=1
    git filter-branch --force --tree-filter "if [ -f src/config.py ]; then sed -i.bak 's|AccountKey=2/ISQ/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu/d6UA==|AccountKey=[REMOVED_SECRET]|g' src/config.py && rm -f src/config.py.bak; fi" --prune-empty --tag-name-filter cat -- --all
    
    Write-Host ""
    Write-Host "Step 3: Cleaning up..." -ForegroundColor Green
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
} else {
    Write-Host ""
    Write-Host "Step 2: Creating secrets file for BFG..." -ForegroundColor Green
    "AccountKey=2/ISQ/w7iTwGLYkGTc5h9Ly4rso1IKwADrcGqQnRvLsaNCryk4duOKUgJawXhXBuDdN0MJhM0a73+AStu/d6UA===>AccountKey=[REMOVED_SECRET]" | Out-File -Encoding ASCII secrets.txt
    
    Write-Host ""
    Write-Host "Step 3: Running BFG to remove secret from all history..." -ForegroundColor Yellow
    Invoke-Expression "$bfgCommand --replace-text secrets.txt ."
    
    Write-Host ""
    Write-Host "Step 4: Cleaning up..." -ForegroundColor Green
    Remove-Item secrets.txt -ErrorAction SilentlyContinue
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
}

Write-Host ""
Write-Host "Step 5: Verifying secret is removed..." -ForegroundColor Green
$found = git log --all --branches --tags -p | Select-String "2/ISQ"
if ($found) {
    Write-Host "WARNING: Secret still found in some commits!" -ForegroundColor Red
    Write-Host "You may need to check other branches or use a different method." -ForegroundColor Yellow
} else {
    Write-Host "Secret successfully removed from all history!" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Review changes: git log --all" -ForegroundColor White
Write-Host "2. Force push ALL branches: git push --force --all" -ForegroundColor White
Write-Host "3. Force push tags: git push --force --tags" -ForegroundColor White
Write-Host "4. Rotate Azure Storage Account key in Azure Portal" -ForegroundColor Red
Write-Host ""
Write-Host "WARNING: Force push will overwrite remote history!" -ForegroundColor Red
Write-Host "Make sure you have a backup and coordinate with your team." -ForegroundColor Yellow
