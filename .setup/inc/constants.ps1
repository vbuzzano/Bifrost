# ============================================================================
# Constants and helper functions for inc/ modules
# ============================================================================
# This file provides small helpers to avoid repeating filenames and to allow
# dot-sourcing inc files without typing the .ps1 extension everywhere.
# ============================================================================

# Expected: $IncDir is set by the caller (functions.ps1 loader)

# Common filenames (can be referenced by other scripts)
$script:ConfigFileName = 'config.psd1'
$script:UserConfigFileName = 'setup.config.psd1'
$script:MakefileTemplateName = '.setup/template/Makefile.template'

function Get-IncPath {
    param([string]$Name)
    if (-not $script:IncDir) {
        throw "Get-IncPath: `$script:IncDir is not set"
    }
    return Join-Path $script:IncDir ("$Name.ps1")
}

function Source-Inc {
    param([string]$Name)
    $path = Get-IncPath $Name
    if (-not (Test-Path $path)) {
        throw "Source-Inc: file not found: $path"
    }
    . $path
}

# Convenience: dot-source by relative path without extension
function Source-Rel {
    param([string]$RelativePath)
    $full = Join-Path $script:IncDir $RelativePath
    if (-not $full.EndsWith('.ps1')) { $full += '.ps1' }
    if (-not (Test-Path $full)) { throw "Source-Rel: not found: $full" }
    . $full
}
