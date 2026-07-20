# ============================================================================
# Command Functions (Invoke-*)
# ============================================================================

function Invoke-Install {
    # Run wizard if config doesn't exist
    if ($NeedsWizard) {
        if (-not (Invoke-ConfigWizard)) {
            return
        }
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "  $($Config.Project.Name) Setup" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Magenta
    
    # Run install script if exists
    $installScript = Join-Path $SetupDir "install.ps1"
    if (Test-Path $installScript) {
        & $installScript
    } else {
        # Inline install
        Create-Directories
        Ensure-SevenZip
        
        foreach ($pkg in $AllPackages) {
            Process-Package $pkg
        }
        
        Cleanup-Temp
        Setup-Makefile
        Generate-AllEnvFiles
        
        Show-InstallComplete
    }
}

function Invoke-Uninstall {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  Uninstall Environment" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    
    $uninstallScript = Join-Path $SetupDir "uninstall.ps1"
    if (Test-Path $uninstallScript) {
        & $uninstallScript
    } else {
        Do-Uninstall
    }
}

function Invoke-Env {
    param([string]$Sub, [string[]]$Params)
    
    switch ($Sub) {
        "list" {
            Show-EnvList
        }
        "update" {
            Generate-AllEnvFiles
            Write-Host "[OK] .env updated" -ForegroundColor Green
        }
        default {
            Write-Host "Unknown env subcommand: $Sub" -ForegroundColor Red
            Write-Host "Use: list, update" -ForegroundColor Gray
            exit 1
        }
    }
}

function Invoke-Pkg {
    param([string]$Sub)
    
    switch ($Sub) {
        "list" {
            Show-PackageList
        }
        "update" {
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Cyan
            Write-Host "  Update Packages" -ForegroundColor Cyan
            Write-Host "========================================" -ForegroundColor Cyan
            
            Ensure-SevenZip
            
            foreach ($pkg in $AllPackages) {
                Process-Package $pkg
            }
            
            # Only update env files, not Makefile
            Generate-AllEnvFiles
            
            Write-Host ""
            Write-Host "[OK] Packages updated" -ForegroundColor Green
        }
        default {
            Write-Host " Unknown pkg subcommand: $Sub" -ForegroundColor Red
            Write-Host "Use: list, update" -ForegroundColor Gray
            exit 1
        }
    }
}
