# ============================================================================
# Project Configuration Wizard
# ============================================================================
# Called by Invoke-Install when setup.config.psd1 doesn't exist.
# ============================================================================

function Invoke-ConfigWizard {
    if (-not (Test-Path $UserConfigTemplate)) {
        Write-Host "User config template not found: $($SysConfig.UserConfigTemplate)" -ForegroundColor Red
        return $false
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Project Configuration" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Get folder name as default
    $folderName = Split-Path $BaseDir -Leaf

    # Ask for project info (only essential)
    Write-Host "Project name" -ForegroundColor Yellow -NoNewline
    Write-Host " [$folderName]: " -ForegroundColor DarkGray -NoNewline
    $projectName = Read-Host
    if ([string]::IsNullOrWhiteSpace($projectName)) { $projectName = $folderName }
    
    Write-Host "Description" -ForegroundColor Yellow -NoNewline
    Write-Host " [Amiga program]: " -ForegroundColor DarkGray -NoNewline
    $description = Read-Host
    if ([string]::IsNullOrWhiteSpace($description)) { $description = "Amiga program" }
    
    Write-Host "Version" -ForegroundColor Yellow -NoNewline
    Write-Host " [1.0.0]: " -ForegroundColor DarkGray -NoNewline
    $version = Read-Host
    if ([string]::IsNullOrWhiteSpace($version)) { $version = "1.0.0" }
    
    Write-Host ""
    
    # Read template and replace placeholders
    $templateContent = Get-Content $UserConfigTemplate -Raw
    $templateContent = $templateContent -replace 'Name\s*=\s*"MyProgram"', "Name        = `"$projectName`""
    $templateContent = $templateContent -replace 'Description\s*=\s*"Program Description"', "Description = `"$description`""
    $templateContent = $templateContent -replace 'Version\s*=\s*"0\.1\.0"', "Version     = `"$version`""
    $templateContent = $templateContent -replace 'ProgramName\s*=\s*"MyProgram"', "ProgramName = `"$projectName`""
    
    $templateContent | Out-File $UserConfigFile -Encoding UTF8
    Write-Host "[OK] Created setup.config.psd1" -ForegroundColor Green
    Write-Host ""
    
    # Load the new config
    $script:UserConfig = Import-PowerShellDataFile $UserConfigFile
    $script:Config = Merge-Config -SysConfig $SysConfig -UserConfig $UserConfig
    
    return $true
}
