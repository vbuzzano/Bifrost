# ============================================================================
# Package Management Functions
# ============================================================================

function Remove-Package {
    param([string]$Name)
    
    $pkgState = Get-PackageState $Name
    if (-not $pkgState) { return }
    
    if ($pkgState.installed -and $pkgState.files) {
        foreach ($file in $pkgState.files) {
            if (Test-Path $file) {
                Remove-Item $file -Recurse -Force -ErrorAction SilentlyContinue
                Write-Info "Removed: $file"
            }
        }
    }
    
    Remove-PackageState $Name
}

function Process-Package {
    param([hashtable]$Item)
    
    $name = $Item.Name
    $mode = if ($Item.Mode) { $Item.Mode } else { "auto" }
    $pkgState = Get-PackageState $name
    $isInstalled = $pkgState -and $pkgState.installed
    $isManual = $pkgState -and -not $pkgState.installed
    $existingEnvs = if ($pkgState -and $pkgState.envs) { $pkgState.envs } else { @{} }
    
    Write-Step "$name - $($Item.Description)"
    
    # Already installed -> ask: Skip, Reinstall, Manual
    if ($isInstalled) {
        $choice = Ask-Choice "$name already installed. [S]kip / [R]einstall / [M]anual?"
        
        switch ($choice) {
            "S" {
                Write-Info "Skipped"
                return
            }
            "R" {
                Write-Info "Removing previous installation..."
                Remove-Package $name
                # Continue to install below
            }
            "M" {
                $envs = Ask-ManualEnvs -ExtractRules $Item.Extract -ExistingEnvs $existingEnvs
                Set-PackageState -Name $name -Installed $false -Files @() -Dirs @() -Envs $envs
                Write-Success "Manual paths configured"
                return
            }
        }
    }
    # Manual config exists -> ask: Skip, Install, Reconfigure
    elseif ($isManual) {
        $choice = Ask-Choice "$name has manual config. [S]kip / [I]nstall / [R]econfigure?"
        
        switch ($choice) {
            "S" {
                Write-Info "Skipped"
                return
            }
            "I" {
                # Continue to install below
            }
            "R" {
                $envs = Ask-ManualEnvs -ExtractRules $Item.Extract -ExistingEnvs $existingEnvs
                Set-PackageState -Name $name -Installed $false -Files @() -Dirs @() -Envs $envs
                Write-Success "Manual paths reconfigured"
                return
            }
        }
    }
    # Not installed -> ask if mode=ask, otherwise auto-install
    else {
        if ($mode -eq "ask") {
            $choice = Ask-Choice "Install? [Y/n]"
            
            if ($choice -eq "N") {
                $envs = Ask-ManualEnvs -ExtractRules $Item.Extract -ExistingEnvs $existingEnvs
                Set-PackageState -Name $name -Installed $false -Files @() -Dirs @() -Envs $envs
                Write-Success "Manual paths configured"
                return
            }
        }
        # mode=auto or user said Yes -> continue to install
    }
    
    # Download and install
    $archive = Download-File -Url $Item.Url -FileName $Item.File
    
    if (-not $archive) {
        Write-Err "Download failed for $name"
        return
    }
    
    if ($Item.Archive -eq "file") {
        $result = Install-SingleFile -FilePath $archive -Name $name -ExtractRules $Item.Extract
    } else {
        $result = Extract-Package -Archive $archive -Name $name -ArchiveType $Item.Archive -ExtractRules $Item.Extract
    }
    
    Set-PackageState -Name $name -Installed $true -Files $result.Files -Dirs $result.Dirs -Envs $result.Envs
    Write-Success "Installed"
}

function Show-PackageList {
    Write-Host ""
    Write-Host "Packages:" -ForegroundColor Cyan
    Write-Host ""
    
    $state = Load-State
    
    # Table columns
    $colName = 20
    $colEnv = 18
    $colValue = 35
    $colStatus = 9
    
    Write-Host ("  {0,-$colName} {1,-$colEnv} {2,-$colValue} {3}" -f "NAME", "ENV VARS", "DESCRIPTION", "INSTALLED") -ForegroundColor DarkGray
    Write-Host ("  {0,-$colName} {1,-$colEnv} {2,-$colValue} {3}" -f ("-" * $colName), ("-" * $colEnv), ("-" * $colValue), ("-" * $colStatus)) -ForegroundColor DarkGray
    
    foreach ($item in $AllPackages) {
        $name = $item.Name
        $pkgState = if ($state.packages.ContainsKey($name)) { $state.packages[$name] } else { $null }
        
        # Get ENV vars (from state if installed, from rules if not)
        $envVars = @{}
        if ($pkgState -and $pkgState.envs) {
            $envVars = $pkgState.envs
        } elseif ($item.Extract) {
            foreach ($rule in $item.Extract) {
                $parsed = Parse-ExtractRule $rule
                if ($parsed -and $parsed.EnvVar) {
                    $envVars[$parsed.EnvVar] = $null
                }
            }
        }
        
        # Status indicator (last column)
        $isInstalled = $pkgState -and $pkgState.installed
        $isManual = $pkgState -and -not $pkgState.installed
        $hasEnvVars = $envVars.Count -gt 0
        $statusMark = if ($isInstalled) { [char]0x1F60A } elseif ($isManual) { [char]0x1F4E6 } else { "" }
        $statusColor = if ($isInstalled) { "Green" } elseif ($isManual) { "Yellow" } else { "DarkGray" }
        
        # First line: package name + first ENV or description
        $firstEnv = $envVars.Keys | Select-Object -First 1
        
        Write-Host ("  {0,-$colName}" -f $name) -ForegroundColor White -NoNewline

        if ($firstEnv) {
            $firstValue = if ($envVars[$firstEnv]) { $envVars[$firstEnv] } else { $item.Description }
            $valueColor = if ($envVars[$firstEnv]) { "Gray" } else { "DarkGray" }
            Write-Host (" {0,-$colEnv}" -f $firstEnv) -ForegroundColor Cyan -NoNewline
            Write-Host (" {0,-$colValue}" -f $firstValue) -ForegroundColor $valueColor -NoNewline
        } else {
            Write-Host (" {0,-$colEnv} {1,-$colValue}" -f "", $item.Description) -ForegroundColor DarkGray -NoNewline
        }
        Write-Host $statusMark -ForegroundColor $statusColor
        
        # Additional ENV vars (skip first)
        $remaining = $envVars.Keys | Select-Object -Skip 1
        foreach ($envName in $remaining) {
            $envValue = if ($envVars[$envName]) { $envVars[$envName] } else { $item.Description }
            $valueColor = if ($envVars[$envName]) { "Gray" } else { "DarkGray" }
            
            Write-Host ("  {0,-$colName}" -f "") -NoNewline
            Write-Host (" {0,-$colEnv}" -f $envName) -ForegroundColor Cyan -NoNewline
            Write-Host (" {0,-$colValue}" -f $envValue) -ForegroundColor $valueColor
        }
    }
    
    Write-Host ""
}
