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


Write-Output "------------------------------------------------------------------"
Write-Output "Build Release: $env:PROGRAM_NAME Version: $env:PROGRAM_VERSION"
Write-Output "------------------------------------------------------------------"

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

# PC SERVER: refresh main.py's generated constants block (no marker - a
# plain value, since it's executed directly as `python main.py`) and the
# ~[VAR]~ version stamp in every other server/*.py file's docstring header
# (safe as a marker there - never executed, just documentation)
. $EnvReplace -Force -Path "server\*.py"

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
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($readmePath, $lf, $utf8NoBom)
Copy-Item -Force "$env:ASSETS_DIR\Ascii.info" "$env:DIST_DIR\$ReleaseDir.readme.info"

## Folder icon (sits next to the $ReleaseDir/ dir in the archive, not inside it)
Copy-Item -Force "$env:ASSETS_DIR\Drawer.info" "$env:DIST_DIR\$ReleaseDir.info"


# Create LHA archive
Set-Location $env:DIST_DIR
. ..\$env:LHATOOL -a "$ReleaseDir.lha" "$ReleaseDir\$env:PROGRAM_EXE_NAME" "$ReleaseDir\Install" "$ReleaseDir\Install.info" "$ReleaseDir\$env:PROGRAM_NAME.guide" "$ReleaseDir\$env:PROGRAM_NAME.guide.info" "$ReleaseDir.info" "$ReleaseDir.readme" "$ReleaseDir.readme.info"
. ..\$env:LHATOOL -l "$ReleaseDir.lha"
Set-Location ..

# ============================================================================
# GitHub release ZIP: Amiga client (.lha) + PC server (source) in one
# archive, so a single download covers both sides.
# ============================================================================

$FullZipDir = "$env:DIST_DIR\$ReleaseDir-full"
New-Item -ItemType Directory -Path "$FullZipDir\BifrostServer" -Force -ErrorAction Stop | Out-Null
Copy-Item -Force "$env:DIST_DIR\$ReleaseDir.lha" "$FullZipDir\"
Copy-Item -Force "README.md" "$FullZipDir\"
Copy-Item -Force "server\*.py" "$FullZipDir\BifrostServer\" -Exclude "test_*.py"
Copy-Item -Force "server\requirements.txt", `
                  "server\setup_venv.ps1", "server\setup_venv.sh", `
                  "server\start_bifrost.bat", "server\start_bifrost.sh", "server\start_bifrost.vbs", `
                  "server\install_startup.ps1", "server\uninstall_startup.ps1" `
                  "$FullZipDir\BifrostServer\"

# Release config: ship the tracked documented-defaults file, never the
# local working copy (server\bifrost_config.json is gitignored precisely
# because it carries personal overrides like right_amiga=ctrl for a
# keyboard with no physical Right Windows key, or debug.enabled=true)
Copy-Item -Force "server\bifrost_config.default.json" "$FullZipDir\BifrostServer\bifrost_config.json"

Compress-Archive -Force -Path "$FullZipDir\*" -DestinationPath "$env:DIST_DIR\$ReleaseDir.zip"
Remove-Item -Force -Recurse $FullZipDir

# ============================================================================
# Two release flavors from here:
#   - GitHub: "$ReleaseDir.zip" (versioned name, e.g. Bifrost-0.3.zip) stays
#     in dist/ as-is - this is what gets attached to a GitHub release. The
#     .lha lives inside it; there's no loose .lha anywhere in dist/.
#   - Aminet: filenames without the version (Aminet tracks versions itself,
#     re-uploading under the same name each time) - built into dist/Aminet/.
# ============================================================================

New-Item -ItemType Directory -Path "$env:DIST_DIR\Aminet" -Force -ErrorAction Stop | Out-Null
# No loose .lha here - it already travels inside $ReleaseDir.zip
Copy-Item -Force "$env:DIST_DIR\$ReleaseDir.zip" "$env:DIST_DIR\Aminet\$env:PROGRAM_NAME.zip"
Move-Item -Force "$env:DIST_DIR\$ReleaseDir.readme" "$env:DIST_DIR\Aminet\$env:PROGRAM_NAME.readme"

# Clean up intermediate versioned artifacts - the .lha travels inside $ReleaseDir.zip, no loose copy needed
Remove-Item -Force -Recurse "$env:DIST_DIR\$ReleaseDir.readme.info"
Remove-Item -Force -Recurse "$env:DIST_DIR\$ReleaseDir"
Remove-Item -Force "$env:DIST_DIR\$ReleaseDir.info"
Remove-Item -Force "$env:DIST_DIR\$ReleaseDir.lha"
