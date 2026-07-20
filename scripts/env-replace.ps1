
# env-replace.ps1
# Usage: pwsh ./tools/env-replace.ps1 -Path <pattern|dir|file> [-Recurse] [-Prefix PROGRAM] [-OutputDir <dir>] [-Force]
# 
# Markdown tag convention:
#   []($PROGRAM_NAME)XMouseD[]()
# - In-place: tag is preserved (for regeneration)
# - OutputDir: tag is replaced by the value (e.g. XMouseD)

param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$Path = ".",
    [switch]$Recurse = $false,
    [string]$Prefix = "PROGRAM",
    [string]$OutputDir = $null,
    [switch]$Force = $false
)

$ErrorActionPreference = 'Stop'

# --- Parse .env ---
$envFile = ".env"

if (!(Test-Path $envFile)) { throw ".env file not found in current directory." }
$envVars = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^$Prefix[_]?([A-Za-z0-9_]+)=(.*)$") {
        $key = "$Prefix".TrimEnd('_') + "_" + $matches[1]
        $envVars[$key] = $matches[2]
    }
}

if ($envVars.Count -eq 0) { throw ".env: no variable found with prefix $Prefix" }

# --- Find files to process ---
$files = @()
if (Test-Path $Path -PathType Container) {
    $files = Get-ChildItem -Path $Path -File -Recurse:$Recurse
} elseif ($Path -like '*[*?]*') {
    $files = Get-ChildItem -Path $Path -File -Recurse:$Recurse
} elseif (Test-Path $Path -PathType Leaf) {
    $files = @(Get-Item $Path)
} else {
    throw "Path $Path not found."
}

if ($files.Count -eq 0) { throw "No file to process for $Path" }



if ($PSBoundParameters.ContainsKey('Path')) {
    $displayPath = $Path
} else {
    $displayPath = (Get-Location).Path
}
Write-Host "[env-replace] Path used: $displayPath"
if ($files.Count -gt 10) {
    Write-Host "[env-replace] $($files.Count) files to process. (list hidden)"
} else {
    Write-Host "[env-replace] Files to process:"
    foreach ($f in $files) { Write-Host " - $($f.FullName)" }
}

 # --- Prepare OutputDir ---
if ($OutputDir) {
    if (!(Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir | Out-Null }
}

foreach ($file in $files) {
    # Detect text file (even without extension)
    $isText = $true
    try {
        $stream = [System.IO.File]::OpenRead($file.FullName)
        $buffer = New-Object byte[] 512
        $read = $stream.Read($buffer, 0, 512)
        $stream.Close()
        $sample = [System.Text.Encoding]::UTF8.GetString($buffer,0,$read)
        if ($sample -match "[\x00-\x08\x0B\x0E-\x1F]" -and $sample -notmatch "\r|\n|\t") {
            $isText = $false
        }
    } catch { $isText = $false }
    if (-not $isText) {
        Write-Host "[env-replace] Skipped (not text): $file"
        continue
    }
    $text = Get-Content $file.FullName -Raw
    
    # Handle ~value[VAR_ENV_NAME]~ syntax FIRST
    # In-place mode (no -OutputDir): ~old[VAR]~ → ~new[VAR]~ (preserve tags)
    # Release mode (-OutputDir): ~old[VAR]~ → new (strip tags)
    $text = [regex]::Replace($text, '~([^\[~]*?)(\[[^\]]+\]~)', {
        param($m)
        $tag = $m.Groups[2].Value  # [PROGRAM_AUTHOR]~ with original case
        $var = $tag -replace '[\[\]~]', ''
        
        # Find matching key (case-insensitive)
        $matchedKey = $envVars.Keys | Where-Object { $_ -ieq $var } | Select-Object -First 1
        if ($matchedKey) {
            $newValue = $envVars[$matchedKey]
            
            if ($OutputDir) {
                # Release mode: strip tags completely
                return $newValue
            } else {
                # In-place mode: preserve tags
                return "~ $newValue $tag"
            }
        }
        
        return $m.Value
    })
    
    # Replace #define VAR_ENV_NAME ...
    # Always quote values for C strings (even if they look like numbers)
    foreach ($k in $envVars.Keys) {
        $pattern = "(?m)^[ \t]*#define[ \t]+$k[ \t]+.*$"
        $v = $envVars[$k]
        $replace = ('#define {0} "{1}"' -f $k, $v)
        $text = [regex]::Replace($text, $pattern, $replace)
    }

    # Handle Markdown tags []($VAR)val[]()
    # Regex: \[\]\(\$(\w+)\)(.*?)\[\]\(\)
    $text = [regex]::Replace($text, '\[\]\(\$(\w+)\)(.*?)\[\]\(\)', {
        param($m)
        $var = $m.Groups[1].Value
        $val = $m.Groups[2].Value
        if ($OutputDir) {
            if ($envVars.ContainsKey($var)) {
                return $envVars[$var]
            } else {
                return $val
            }
        } else {
            # In-place: preserve the tag, but replace the value between tags if possible
            if ($envVars.ContainsKey($var)) {
                return "[]($" + $var + ")" + $envVars[$var] + "[]()"
            } else {
                return $m.Value
            }
        }
    })

    # Save
    if ($OutputDir) {
        # Copy to OutputDir (strip tags)
        $dest = Join-Path $OutputDir $file.Name
        if ((Test-Path $dest) -and -not $Force) {
            Write-Error "-Force required to overwrite: $dest" -ErrorAction Stop
        }
        Set-Content $dest $text -NoNewline
        Write-Host "[env-replace] $file -> $dest"
    } else {
        # In-place edit (preserve tags)
        if (-not $Force) { 
            Write-Error "-Force required to overwrite: $($file.Name)" -ErrorAction Stop
        }
        Set-Content $file.FullName $text -NoNewline
        Write-Host "[env-replace] $file (in-place)"
    }
}
Write-Host "[env-replace] Done."
