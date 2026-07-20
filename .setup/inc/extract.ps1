# ============================================================================
# Extract Functions
# ============================================================================

function Parse-ExtractRule {
    param([string]$Rule)
    
    # Format: TYPE:pattern:destination[:ENV_VAR]
    $parts = $Rule -split ":"
    
    if ($parts.Count -lt 3) {
        Write-Warn "Invalid rule format: $Rule"
        return $null
    }
    
    return @{
        Type = $parts[0]
        Pattern = $parts[1]
        Destination = $parts[2]
        EnvVar = if ($parts.Count -ge 4) { $parts[3] } else { $null }
    }
}

function Copy-WithPattern {
    param(
        [string]$Source,
        [string]$Pattern,
        [string]$Destination
    )
    
    $destPath = Join-Path $BaseDir $Destination
    $destIsFile = -not $Destination.EndsWith("/") -and [System.IO.Path]::HasExtension($Destination)
    
    $createdDirs = @()
    
    if ($destIsFile) {
        $destDir = Split-Path $destPath -Parent
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            $createdDirs += $destDir
        }
    } else {
        if (-not (Test-Path $destPath)) {
            New-Item -ItemType Directory -Path $destPath -Force | Out-Null
            $createdDirs += $destPath
        }
    }
    
    $copiedFiles = @()
    
    # Handle "dir/*" pattern
    if ($Pattern -match '^(.+)/\*$') {
        $subDir = $Matches[1]
        $srcPath = Join-Path $Source $subDir
        if (Test-Path $srcPath) {
            Get-ChildItem -Path $srcPath -Force | ForEach-Object {
                $itemDest = Join-Path $destPath $_.Name
                if ($_.PSIsContainer) {
                    Copy-Item $_.FullName -Destination $itemDest -Recurse -Force
                } else {
                    Copy-Item $_.FullName -Destination $itemDest -Force
                }
                $copiedFiles += $itemDest
            }
            Write-Info "Copied $subDir/* -> $Destination"
        }
    }
    # Handle "**/*.ext" or "**/filename" pattern
    elseif ($Pattern -match '^\*\*/(.+)$') {
        $filePattern = $Matches[1]
        Get-ChildItem -Path $Source -Recurse -Filter $filePattern -File -ErrorAction SilentlyContinue | ForEach-Object {
            if ($destIsFile) {
                Copy-Item $_.FullName -Destination $destPath -Force
                $copiedFiles += $destPath
            } else {
                $target = Join-Path $destPath $_.Name
                Copy-Item $_.FullName -Destination $target -Force
                $copiedFiles += $target
            }
            Write-Info "Copied $($_.Name)"
        }
    }
    # Handle "*" pattern
    elseif ($Pattern -eq "*") {
        Get-ChildItem -Path $Source -Force | ForEach-Object {
            $itemDest = Join-Path $destPath $_.Name
            if ($_.PSIsContainer) {
                Copy-Item $_.FullName -Destination $itemDest -Recurse -Force
            } else {
                Copy-Item $_.FullName -Destination $itemDest -Force
            }
            $copiedFiles += $itemDest
        }
        Write-Info "Copied all -> $Destination"
    }
    # Specific file pattern
    else {
        Get-ChildItem -Path $Source -Recurse -Filter $Pattern -File -ErrorAction SilentlyContinue | ForEach-Object {
            if ($destIsFile) {
                Copy-Item $_.FullName -Destination $destPath -Force
                $copiedFiles += $destPath
            } else {
                $target = Join-Path $destPath $_.Name
                Copy-Item $_.FullName -Destination $target -Force
                $copiedFiles += $target
            }
            Write-Info "Copied $($_.Name)"
        }
    }
    
    return @{
        Files = $copiedFiles
        Dirs = $createdDirs
    }
}

function Extract-Package {
    param(
        [string]$Archive,
        [string]$Name,
        [string]$ArchiveType,
        [array]$ExtractRules
    )
    
    $tempExtract = Join-Path $TempDir $Name
    
    # Clean temp
    if (Test-Path $tempExtract) {
        Remove-Item $tempExtract -Recurse -Force
    }
    New-Item -ItemType Directory -Path $tempExtract -Force | Out-Null
    
    # Extract
    Write-Info "Extracting $ArchiveType..."
    $result = & $SevenZipExe x $Archive -o"$tempExtract" -y 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Extraction warning: $result"
    }
    
    $allFiles = @()
    $allDirs = @()
    $allEnvs = @{}
    
    # Process each extract rule - save state after each rule for crash recovery
    foreach ($rule in $ExtractRules) {
        $parsed = Parse-ExtractRule $rule
        if (-not $parsed) { continue }
        
        $copyResult = Copy-WithPattern -Source $tempExtract -Pattern $parsed.Pattern -Destination $parsed.Destination
        $allFiles += $copyResult.Files
        $allDirs += $copyResult.Dirs
        
        if ($parsed.EnvVar) {
            $allEnvs[$parsed.EnvVar] = $parsed.Destination
        }
        
        # Save state incrementally after each rule (crash recovery)
        Set-PackageState -Name $Name -Installed $true -Files $allFiles -Dirs $allDirs -Envs $allEnvs
    }
    
    # Cleanup
    Remove-Item $tempExtract -Recurse -Force -ErrorAction SilentlyContinue
    
    return @{
        Files = $allFiles
        Dirs = $allDirs
        Envs = $allEnvs
    }
}

function Install-SingleFile {
    param(
        [string]$FilePath,
        [string]$Name,
        [array]$ExtractRules
    )
    
    $allFiles = @()
    $allDirs = @()
    $allEnvs = @{}
    
    foreach ($rule in $ExtractRules) {
        $parsed = Parse-ExtractRule $rule
        if (-not $parsed) { continue }
        
        $destPath = Join-Path $BaseDir $parsed.Destination
        
        if ([System.IO.Path]::HasExtension($parsed.Destination)) {
            $destDir = Split-Path $destPath -Parent
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                $allDirs += $destDir
            }
            Copy-Item $FilePath -Destination $destPath -Force
        } else {
            if (-not (Test-Path $destPath)) {
                New-Item -ItemType Directory -Path $destPath -Force | Out-Null
                $allDirs += $destPath
            }
            $fileName = Split-Path $FilePath -Leaf
            $destPath = Join-Path $destPath $fileName
            Copy-Item $FilePath -Destination $destPath -Force
        }
        
        $allFiles += $destPath
        Write-Info "Copied to $($parsed.Destination)"
        
        if ($parsed.EnvVar) {
            $allEnvs[$parsed.EnvVar] = $parsed.Destination
        }
        
        # Save state incrementally after each rule (crash recovery)
        Set-PackageState -Name $Name -Installed $true -Files $allFiles -Dirs $allDirs -Envs $allEnvs
    }
    
    return @{
        Files = $allFiles
        Dirs = $allDirs
        Envs = $allEnvs
    }
}

function Get-EnvVarsFromRules {
    param([array]$ExtractRules)
    
    $envs = @{}
    foreach ($rule in $ExtractRules) {
        $parsed = Parse-ExtractRule $rule
        if ($parsed -and $parsed.EnvVar) {
            $envs[$parsed.EnvVar] = $null
        }
    }
    return $envs
}

function Ask-ManualEnvs {
    param(
        [array]$ExtractRules,
        [hashtable]$ExistingEnvs = @{}
    )
    
    $envs = @{}
    $needsInput = $false
    
    foreach ($rule in $ExtractRules) {
        $parsed = Parse-ExtractRule $rule
        if ($parsed -and $parsed.EnvVar) {
            if ($ExistingEnvs.ContainsKey($parsed.EnvVar) -and $ExistingEnvs[$parsed.EnvVar]) {
                $envs[$parsed.EnvVar] = $ExistingEnvs[$parsed.EnvVar]
                Write-Info "Using existing: $($parsed.EnvVar) = $($ExistingEnvs[$parsed.EnvVar])"
            } else {
                $needsInput = $true
            }
        }
    }
    
    if ($needsInput) {
        Write-Info "Please provide paths for required variables:"
        
        foreach ($rule in $ExtractRules) {
            $parsed = Parse-ExtractRule $rule
            if ($parsed -and $parsed.EnvVar -and -not $envs.ContainsKey($parsed.EnvVar)) {
                $path = Ask-Path $parsed.EnvVar
                if ($path.StartsWith($BaseDir)) {
                    $path = $path.Substring($BaseDir.Length + 1).Replace('\', '/')
                }
                $envs[$parsed.EnvVar] = $path
            }
        }
    }
    
    return $envs
}
