# ============================================================================
# AmigaDevBox - Setup Functions Loader
# ============================================================================
# This file loads all modular function files
# DO NOT MODIFY - changes will be overwritten on updates
# ============================================================================

# Determine inc directory. Prefer $SetupDir if provided by the caller,
# otherwise fall back to script location.
if ($SetupDir) {
    $script:IncDir = Join-Path $SetupDir "inc"
} else {
    $script:IncDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

# Load all modules directly (dot-source must be at script level, not inside a function)
. "$script:IncDir\constants.ps1"
. "$script:IncDir\common.ps1"
. "$script:IncDir\sevenzip.ps1"
. "$script:IncDir\download.ps1"
. "$script:IncDir\extract.ps1"
. "$script:IncDir\makefile.ps1"
. "$script:IncDir\envs.ps1"
. "$script:IncDir\packages.ps1"
. "$script:IncDir\directories.ps1"
. "$script:IncDir\ui.ps1"
. "$script:IncDir\help.ps1"
. "$script:IncDir\wizard.ps1"
. "$script:IncDir\commands.ps1"
