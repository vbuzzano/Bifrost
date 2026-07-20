# build-release.ps1
# Usage: pwsh /build-release.ps1 -Path <pattern|dir|file> [-Recurse] [-Prefix PROGRAM] [-OutputDir <dir>] [-Force]

# check for setup script
$Setup = "$pwd\setup.ps1"
if (!(Test-Path $Setup)) {
    $Setup = "$pwd\scripts\setup.ps1"
    if (!(Test-Path $Setup)) {
        throw "setup.ps1 introuvable dans les dossiers scripts ou racine."
    }
}

# check for env-replace script
$EnvReplace = "$pwd\env-replace.ps1"
if (!(Test-Path $EnvReplace)) {
    $EnvReplace = "$pwd\scripts\env-replace.ps1"
    if (!(Test-Path $EnvReplace)) {
        throw "env-replace.ps1 introuvable dans les dossiers scripts ou racine."
    }
}

# update env
. $Setup env update

# Load .env file into environment
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#=]+?)\s*=\s*(.+?)\s*$') {
        $name = $matches[1]
        $value = $matches[2]
        # Supprimer les guillemets si présents
        $value = $value -replace '^["'']|["'']$', ''
        # Définir comme variable d'environnement
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        # Ou créer une variable dans le scope actuel
        Set-Variable -Name $name -Value $value -Scope Script
    }
}

$escapedVersion = $env:PROGRAM_VERSION -replace '[^A-Za-z0-9._-]', '_'
$ReleaseDir = "$env:PROGRAM_NAME-$escapedVersion"

# UPDATE FILES (in-place: updates template values, preserves markers)
. $EnvReplace -Force -Path "$env:PROGRAM_EXE_NAME.readme"
. $EnvReplace -Force -Path "$env:PROGRAM_EXE_NAME.guide"
. $EnvReplace -Force -Path "Install"
# Optional: only run if the project actually has markdown docs to process
if (Test-Path "docs\*.md") { . $EnvReplace -Force -Path "docs\*.md" }
if (Get-ChildItem -Path "." -Filter "*.md" -File -ErrorAction SilentlyContinue) { . $EnvReplace -Force -Path "*.md" }

# SOURCE: update #define constants from .env
. $EnvReplace  -Recurse -Force -Path ".\src"

# PROGRAM: clean dist/ and rebuild release binary
make MODE=release rebuild

# Create release directory AFTER build (dist/ now exists with only the binary)
New-Item -ItemType Directory -Path "$env:DIST_DIR\$ReleaseDir" -Force -ErrorAction Stop | Out-Null
Move-Item -Force "$env:DIST_DIR\$env:PROGRAM_EXE_NAME" "$env:DIST_DIR\$ReleaseDir"

# GUIDE
. $EnvReplace  -Force -OutputDir ".\dist" -Path "$env:PROGRAM_EXE_NAME.guide"
Move-Item -Force "$env:DIST_DIR\$env:PROGRAM_EXE_NAME.guide" "$env:DIST_DIR\$ReleaseDir\$env:PROGRAM_NAME.guide"
Copy-Item -Force "$env:ASSETS_DIR\Guide.info" "$env:DIST_DIR\$ReleaseDir\$env:PROGRAM_NAME.guide.info"


# INSTALL
. $EnvReplace -Force -OutputDir ".\dist" -Path "Install"
Move-Item -Force "$env:DIST_DIR\Install" "$env:DIST_DIR\$ReleaseDir\Install"
Copy-Item -Force "$env:ASSETS_DIR\Install.info" "$env:DIST_DIR\$ReleaseDir\Install.info"

# README - Aminet requires LF line endings (not CRLF)
. $EnvReplace -Force -OutputDir ".\dist" -Path "$env:PROGRAM_EXE_NAME.readme"
Move-Item -Force "$env:DIST_DIR\$env:PROGRAM_EXE_NAME.readme" "$env:DIST_DIR\$ReleaseDir.readme"
$readmePath = "$env:DIST_DIR\$ReleaseDir.readme"
$lf = [System.IO.File]::ReadAllText($readmePath) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($readmePath, $lf, [System.Text.Encoding]::UTF8)
Copy-Item -Force "$env:ASSETS_DIR\Ascii.info" "$env:DIST_DIR\$ReleaseDir.readme.info"

## Folder icon (sits next to the $ReleaseDir/ dir in the archive, not inside it)
Copy-Item -Force "$env:ASSETS_DIR\Drawer.info" "$env:DIST_DIR\$ReleaseDir.info"


# Create LHA archive
Set-Location $env:DIST_DIR
. ..\$env:LHATOOL -a "$ReleaseDir.lha" "$ReleaseDir\$env:PROGRAM_EXE_NAME" "$ReleaseDir\Install" "$ReleaseDir\Install.info" "$ReleaseDir\$env:PROGRAM_NAME.guide" "$ReleaseDir\$env:PROGRAM_NAME.guide.info" "$ReleaseDir.info" "$ReleaseDir.readme" "$ReleaseDir.readme.info"
. ..\$env:LHATOOL -l "$ReleaseDir.lha"
Set-Location ..

# ============================================================================
# Two release flavors from here:
#   - GitHub: "$ReleaseDir.lha" (versioned name, e.g. Bifrost-0.3.lha) stays
#     in dist/ as-is - this is what gets attached to a GitHub release.
#   - Aminet: filenames without the version (Aminet tracks versions itself,
#     re-uploading under the same name each time) - built into dist/Aminet/.
# ============================================================================

New-Item -ItemType Directory -Path "$env:DIST_DIR\Aminet" -Force -ErrorAction Stop | Out-Null
Copy-Item -Force "$env:DIST_DIR\$ReleaseDir.lha" "$env:DIST_DIR\Aminet\$env:PROGRAM_NAME.lha"
Move-Item -Force "$env:DIST_DIR\$ReleaseDir.readme" "$env:DIST_DIR\Aminet\$env:PROGRAM_NAME.readme"

# Clean up intermediate versioned artifacts (the .lha itself is kept for GitHub)
Remove-Item -Force -Recurse "$env:DIST_DIR\$ReleaseDir.readme.info"
Remove-Item -Force -Recurse "$env:DIST_DIR\$ReleaseDir"
Remove-Item -Force "$env:DIST_DIR\$ReleaseDir.info"
