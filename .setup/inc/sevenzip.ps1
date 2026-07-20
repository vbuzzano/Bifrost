# ============================================================================
# 7-Zip Setup
# ============================================================================

function Ensure-SevenZip {
    if (Test-Path $SevenZipExe) {
        Write-Info "7-Zip already present"
        return
    }
    
    Write-Step "Setting up 7-Zip extractor"
    
    # Create directories
    $sevenZipTempDir = Join-Path $TempDir "7zip"
    @($SetupToolsDir, $CacheDir, $TempDir, $sevenZipTempDir) | ForEach-Object {
        if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
    }
    
    $ProgressPreference = 'SilentlyContinue'
    
    try {
        $sevenZrPath = Join-Path $TempDir "7zr.exe"
        Invoke-WebRequest -Uri "https://www.7-zip.org/a/7zr.exe" -OutFile $sevenZrPath -UseBasicParsing
        Write-Info "Downloaded 7zr.exe"
        
        $installerPath = Join-Path $TempDir "7z2501.exe"
        Invoke-WebRequest -Uri "https://github.com/ip7z/7zip/releases/download/25.01/7z2501.exe" -OutFile $installerPath -UseBasicParsing
        Write-Info "Downloaded 7z2501.exe"
        
        & $sevenZrPath x $installerPath -o"$sevenZipTempDir" -y | Out-Null
        
        Copy-Item (Join-Path $sevenZipTempDir "7z.exe") $SevenZipExe -Force
        Copy-Item (Join-Path $sevenZipTempDir "7z.dll") $SevenZipDll -Force
        
        Write-Success "7-Zip ready"
    }
    catch {
        Write-Err "Failed to setup 7-Zip: $_"
        exit 1
    }
    finally {
        $ProgressPreference = 'Continue'
    }
}
