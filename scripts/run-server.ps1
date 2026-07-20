# Run backend server on PC
$Location = Get-Location
Write-Output "--| ${Location}"

try {
    Set-Location $PSScriptRoot
    Set-Location ..\server
    .\.venv\Scripts\python.exe main.py
}
catch {
    Write-Error "Failed to start Bifrost server: $_"
    Write-Output "Attempting to run with PowerShell..."
}
finally {
    Set-Location $Location
}
