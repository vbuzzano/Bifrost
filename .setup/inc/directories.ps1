# ============================================================================
# Directory Management Functions
# ============================================================================

function Create-Directories {
    Write-Step "Creating project directories"
    
    foreach ($dir in $Config.Directories) {
        $fullPath = Join-Path $BaseDir $dir
        if (-not (Test-Path $fullPath)) {
            New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
            Write-Info "Created: $dir/"
        }
    }
    
    Write-Success "Directories ready"
}

function Cleanup-Temp {
    if (Test-Path $TempDir) {
        Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Info "Cleaned up temp/"
    }
}

function Do-Uninstall {
    Write-Step "Removing installed packages and generated files"
    
    $state = Load-State
    $removedCount = 0
    
    # Remove installed packages (files and dirs tracked in state)
    foreach ($pkgName in @($state.packages.Keys)) {
        $pkgState = $state.packages[$pkgName]
        if ($pkgState.installed) {
            Write-Info "Removing $pkgName..."
            
            # First remove files
            if ($pkgState.files) {
                foreach ($file in $pkgState.files) {
                    if (Test-Path $file) {
                        Remove-Item $file -Recurse -Force -ErrorAction SilentlyContinue
                        $removedCount++
                    }
                }
            }
            
            # Then remove created directories (if empty)
            if ($pkgState.dirs) {
                foreach ($dir in $pkgState.dirs) {
                    Remove-DirectoryIfEmpty -Path $dir
                }
            }
            
            # Clean empty parent directories (bottom-up from files)
            if ($pkgState.files) {
                foreach ($file in $pkgState.files) {
                    $parent = Split-Path $file -Parent
                    Remove-EmptyParents -Path $parent
                }
            }
        }
        Remove-PackageState $pkgName
    }
    
    # Remove generated env files
    @(".env", ".env.custom") | ForEach-Object {
        $path = Join-Path $BaseDir $_
        if (Test-Path $path) {
            Remove-Item $path -Force
            Write-Info "Removed $_"
            $removedCount++
        }
    }
    
    # Remove .setup internal directories (cache, tools)
    @(".setup/cache", ".setup/tools") | ForEach-Object {
        $path = Join-Path $BaseDir $_
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
            Write-Info "Removed $_/"
            $removedCount++
        }
    }
    
    # Always remove build and dist directories
    @("build", "dist") | ForEach-Object {
        $path = Join-Path $BaseDir $_
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
            Write-Info "Removed $_/"
            $removedCount++
        }
    }
    
    # Remove state file last
    $statePath = Join-Path $BaseDir ".setup/state.json"
    if (Test-Path $statePath) {
        Remove-Item $statePath -Force
        Write-Info "Removed .setup/state.json"
    }
    
    if ($removedCount -eq 0) {
        Write-Info "Nothing to remove"
    }
    
    Write-Success "Uninstall complete"
    Write-Host ""
}

# Remove a directory only if it's empty
function Remove-DirectoryIfEmpty {
    param([string]$Path)
    
    if (Test-Path $Path) {
        $items = Get-ChildItem $Path -Force -ErrorAction SilentlyContinue
        if ($items.Count -eq 0) {
            Remove-Item $Path -Force -ErrorAction SilentlyContinue
        }
    }
}

# Remove empty parent directories up to BaseDir
function Remove-EmptyParents {
    param([string]$Path)
    
    while ($Path -and $Path -ne $BaseDir -and (Test-Path $Path)) {
        $items = Get-ChildItem $Path -Force -ErrorAction SilentlyContinue
        if ($items.Count -eq 0) {
            Remove-Item $Path -Force -ErrorAction SilentlyContinue
            $Path = Split-Path $Path -Parent
        } else {
            break
        }
    }
}
