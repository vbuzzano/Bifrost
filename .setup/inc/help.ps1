# ============================================================================
# Help Functions
# ============================================================================

function Show-Help {
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
