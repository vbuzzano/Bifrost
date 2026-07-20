# ============================================================================
# AmigaDevBox - Initialization Module
# ============================================================================
# This file handles all setup initialization: paths, configs, and functions.
# Dot-source this from setup.ps1 to keep the main script clean.
# ============================================================================

# ============================================================================
# Constants (local to init, no $script: needed)
# ============================================================================

$CONFIG_FILENAME = 'config.psd1'
$USER_CONFIG_FILENAME = 'setup.config.psd1'
$STATE_FILENAME = '.setup/state.json'
$FUNCTIONS_LOADER = 'inc\functions.ps1'

# ============================================================================
# Derived Paths (BaseDir and SetupDir are set by caller)
# ============================================================================

$script:StateFile = Join-Path $BaseDir $STATE_FILENAME
$script:EnvFile = Join-Path $BaseDir ".env"

# ============================================================================
# Load Functions (before config loading - needed for Merge-Config)
# ============================================================================

$script:FunctionsLoader = Join-Path $SetupDir $FUNCTIONS_LOADER
if (-not (Test-Path $FunctionsLoader)) {
    Write-Host "Functions loader not found: $FunctionsLoader" -ForegroundColor Red
    exit 1
}
. $FunctionsLoader

# ============================================================================
# Configuration Loading
# ============================================================================

# Load system config
$script:SysConfigFile = Join-Path $SetupDir $CONFIG_FILENAME
if (-not (Test-Path $SysConfigFile)) {
    Write-Host "$CONFIG_FILENAME not found in .setup/" -ForegroundColor Red
    exit 1
}
$script:SysConfig = Import-PowerShellDataFile $SysConfigFile

# User config
$script:UserConfigFile = Join-Path $BaseDir $USER_CONFIG_FILENAME
$script:UserConfigTemplate = Join-Path $BaseDir $SysConfig.UserConfigTemplate

# Handle missing user config based on command
$script:SkipExecution = $false
$script:StateExists = Test-Path (Join-Path $BaseDir $STATE_FILENAME)

# Commands that require state (not install, not help)
if ($SetupCommand -in @("uninstall", "env", "pkg")) {
    if (-not $StateExists) {
        Write-Host ""
        Write-Host "No configuration found." -ForegroundColor Red
        Write-Host "Run 'setup' or 'setup install' first." -ForegroundColor Gray
        Write-Host ""
        $script:SkipExecution = $true
    }
}

# Load config if not skipping
if (-not $SkipExecution) {
    if (Test-Path $UserConfigFile) {
        $script:UserConfig = Import-PowerShellDataFile $UserConfigFile
        $script:Config = Merge-Config -SysConfig $SysConfig -UserConfig $UserConfig
    }
    elseif ($SetupCommand -eq "install" -or $SetupCommand -eq "") {
        # install: will run wizard later in Invoke-Install
        $script:UserConfig = @{}
        $script:Config = $SysConfig
        $script:NeedsWizard = $true
    }
    else {
        # Other commands without config but with state - use minimal config
        $script:UserConfig = @{}
        $script:Config = $SysConfig
    }
}

# ============================================================================
# Derived Paths (from merged config)
# ============================================================================

# Cache path (with override support)
$script:CacheDir = if ($Config.CachePath) { 
    if ([System.IO.Path]::IsPathRooted($Config.CachePath)) { $Config.CachePath } 
    else { Join-Path $BaseDir $Config.CachePath }
} else { 
    Join-Path $BaseDir $Config.SetupPaths.Cache 
}
$script:DownloadsDir = $CacheDir
$script:TempDir = Join-Path $CacheDir "temp"
$script:SetupToolsDir = Join-Path $BaseDir $Config.SetupPaths.Tools

# 7-Zip paths
$script:SevenZipExe = Join-Path $SetupToolsDir "7z.exe"
$script:SevenZipDll = Join-Path $SetupToolsDir "7z.dll"

# All packages (merged - UserConfig.Packages first for priority)
$script:AllPackages = if ($Config.Packages) { $Config.Packages } else { @() }
