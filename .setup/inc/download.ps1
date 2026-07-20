# ============================================================================
# Download Functions
# ============================================================================

function Download-File {
    param(
        [string]$Url,
        [string]$FileName
    )
    
    # Ensure cache directory exists
    if (-not (Test-Path $CacheDir)) {
        New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
    }
    
    $outPath = Join-Path $CacheDir $FileName
    
    if (Test-Path $outPath) {
        Write-Info "Already downloaded: $FileName"
        return $outPath
    }
    
    Write-Info "Downloading $FileName..."
    
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Url -OutFile $outPath -UseBasicParsing -AllowUnencryptedAuthentication -AllowInsecureRedirect
        $ProgressPreference = 'Continue'
        
        $size = [math]::Round((Get-Item $outPath).Length / 1KB, 1)
        Write-Info "Downloaded: $size KB"
        return $outPath
    }
    catch {
        Write-Err "Download failed: $_"
        return $null
    }
}
