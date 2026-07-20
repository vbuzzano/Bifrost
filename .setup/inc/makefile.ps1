# ============================================================================
# Makefile Generation Functions
# ============================================================================

function Setup-Makefile {
    $templatePath = Join-Path $BaseDir $Config.MakefileTemplate
    $makefilePath = Join-Path $BaseDir "Makefile"
    
    if (-not (Test-Path $makefilePath)) {
        if (-not (Test-Path $templatePath)) {
            Write-Warn "Makefile.template not found at $($Config.MakefileTemplate), skipping Makefile creation"
            return
        }
        
        Copy-Item $templatePath $makefilePath -Force
        Write-Success "Created Makefile from template"
    } else {
        Write-Info "Makefile already exists (not modified)"
    }
}
