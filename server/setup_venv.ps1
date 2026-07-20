# Bifrost - Python server venv setup (Windows / PowerShell)
# Run once from the server/ directory:  .\setup_venv.ps1

$VenvDir = ".venv"

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv..."
    python -m venv $VenvDir
}

Write-Host "Installing dependencies..."
& "$VenvDir\Scripts\pip.exe" install -r requirements.txt

Write-Host ""
Write-Host "Done. To start the server:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python main.py"
Write-Host ""
Write-Host "Or without activating:"
Write-Host "  .\.venv\Scripts\python.exe main.py"
