<# 
.SYNOPSIS
    ApolloDevBox Development Environment Setup
    
.DESCRIPTION
    Manages the development environment for AmigaOS cross-compilation.
    
.PARAMETER Command
    The command to execute: install, uninstall, env, pkg, help
    
.EXAMPLE
    .\setup.ps1                    # Install (default)
    .\setup.ps1 install            # Install all
    .\setup.ps1 uninstall          # Uninstall environment
    .\setup.ps1 env list           # List environment variables
    .\setup.ps1 env reset          # Regenerate env files
    .\setup.ps1 env add KEY=VALUE  # Add environment variable
    .\setup.ps1 pkg list           # List packages
    .\setup.ps1 pkg update         # Update packages
    .\setup.ps1 help               # Show help
    
.NOTES
    Author: Vincent Buzzano
    Date: December 2025
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "uninstall", "env", "pkg", "help", "")]
    [string]$Command = "install",
    
    [Parameter(Position = 1)]
    [string]$SubCommand = "",
    
    [Parameter(Position = 2, ValueFromRemainingArguments = $true)]
    [string[]]$Args,
    
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Quick Help (before loading config)
# ============================================================================

function Show-QuickHelp {
    Write-Host ""
    Write-Host "Usage: setup.ps1 [command] [subcommand]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Yellow
    Write-Host "  install          Install all dependencies (default)" -ForegroundColor White
    Write-Host "  uninstall        Remove all generated files (back to factory state)" -ForegroundColor White
    Write-Host "  env              Manage environment variables" -ForegroundColor White
    Write-Host "  pkg              Manage packages" -ForegroundColor White
    Write-Host "  help             Show this help" -ForegroundColor White
    Write-Host ""
    Write-Host "Env subcommands:" -ForegroundColor Yellow
    Write-Host "  env list         List all environment variables" -ForegroundColor White
    Write-Host "  env update       Regenerate .env file" -ForegroundColor White
    Write-Host ""
    Write-Host "Pkg subcommands:" -ForegroundColor Yellow
    Write-Host "  pkg list         List all packages with status" -ForegroundColor White
    Write-Host "  pkg update       Update/install packages interactively" -ForegroundColor White
    Write-Host ""
}

if ($Help -or $Command -eq "help") {
    Show-QuickHelp
    exit 0
}

# ============================================================================
# Base Paths (defined here, used by init.ps1)
# ============================================================================

$_scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path $_scriptDir -Leaf) -eq 'scripts') {
    $script:BaseDir = Split-Path -Parent $_scriptDir
} else {
    $script:BaseDir = $_scriptDir
}
$script:SetupDir = Join-Path $BaseDir ".setup"
$script:SetupCommand = $Command

# ============================================================================
# Initialize (loads configs, functions, and derived paths)
# ============================================================================

$_initPath = Join-Path $SetupDir "inc\\init.ps1"
if (-not (Test-Path $_initPath)) {
    Write-Err "init.ps1 not found: $_initPath"
    exit 1
}
. $_initPath

# Exit early if init signals to skip
if ($SkipExecution) {
    exit 0
}

# ============================================================================
# Main
# ============================================================================

switch ($Command) {
    "install" {
        Invoke-Install
    }
    "uninstall" {
        Invoke-Uninstall
    }
    "env" {
        if ([string]::IsNullOrEmpty($SubCommand)) {
            Show-EnvList
        } else {
            Invoke-Env -Sub $SubCommand -Params $Args
        }
    }
    "pkg" {
        if ([string]::IsNullOrEmpty($SubCommand)) {
            Show-PackageList
        } else {
            Invoke-Pkg -Sub $SubCommand
        }
    }
    default {
        Invoke-Install
    }
}
