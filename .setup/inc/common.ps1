# ============================================================================
# Common Functions - State, Output, User Input, Config Merge
# ============================================================================

# ============================================================================
# Configuration Merge
# ============================================================================

function Merge-Hashtable {
    param(
        [hashtable]$Base,
        [hashtable]$Override
    )
    
    $result = $Base.Clone()
    
    foreach ($key in $Override.Keys) {
        $overrideValue = $Override[$key]
        
        if ($result.ContainsKey($key)) {
            $baseValue = $result[$key]
            
            # Both are hashtables -> recursive merge
            if ($baseValue -is [hashtable] -and $overrideValue -is [hashtable]) {
                $result[$key] = Merge-Hashtable $baseValue $overrideValue
            }
            # Both are arrays -> concatenate (Override first for priority)
            elseif ($baseValue -is [array] -and $overrideValue -is [array]) {
                $result[$key] = $overrideValue + $baseValue
            }
            # Override replaces base
            else {
                $result[$key] = $overrideValue
            }
        }
        else {
            # New key from override
            $result[$key] = $overrideValue
        }
    }
    
    return $result
}

function Merge-Config {
    param(
        [hashtable]$SysConfig,
        [hashtable]$UserConfig
    )
    
    return Merge-Hashtable $SysConfig $UserConfig
}

# ============================================================================
# State Management
# ============================================================================

function Load-State {
    if (Test-Path $StateFile) {
        return Get-Content $StateFile -Raw | ConvertFrom-Json -AsHashtable
    }
    return @{ packages = @{} }
}

function Save-State {
    param([hashtable]$State)
    $State | ConvertTo-Json -Depth 10 | Out-File $StateFile -Encoding UTF8
}

function Get-PackageState {
    param([string]$Name)
    $state = Load-State
    if ($state.packages.ContainsKey($Name)) {
        return $state.packages[$Name]
    }
    return $null
}

function Set-PackageState {
    param(
        [string]$Name,
        [bool]$Installed,
        [array]$Files,
        [array]$Dirs,
        [hashtable]$Envs
    )
    $state = Load-State
    $state.packages[$Name] = @{
        installed = $Installed
        files = $Files
        dirs = if ($Dirs) { $Dirs } else { @() }
        envs = $Envs
        date = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }
    Save-State $state
}

function Remove-PackageState {
    param([string]$Name)
    $state = Load-State
    if ($state.packages.ContainsKey($Name)) {
        $state.packages.Remove($Name)
        Save-State $state
    }
}

# ============================================================================
# Output Functions
# ============================================================================

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Gray
}

function Write-Success {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Green
}

function Write-Err {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Red
}

function Write-Warn {
    param([string]$Message)
    Write-Host "    [WARN] $Message" -ForegroundColor Yellow
}

# ============================================================================
# User Input Functions
# ============================================================================

function Ask-YesNo {
    param(
        [string]$Question,
        [bool]$Default = $true
    )
    $defaultText = if ($Default) { "Y/n" } else { "y/N" }
    $response = Read-Host "$Question [$defaultText]"
    if ([string]::IsNullOrWhiteSpace($response)) { return $Default }
    return $response -match '^[Yy]'
}

function Ask-Choice {
    param(
        [string]$Question,
        [string]$Default = "S"
    )
    $response = Read-Host "$Question"
    if ([string]::IsNullOrWhiteSpace($response)) { return $Default.ToUpper() }
    return $response.Substring(0,1).ToUpper()
}

function Ask-String {
    param(
        [string]$Prompt,
        [string]$Default = "",
        [bool]$Required = $true
    )
    
    $defaultText = if ($Default) { " [$Default]" } else { "" }
    $response = Read-Host "    $Prompt$defaultText"
    
    if ([string]::IsNullOrWhiteSpace($response)) {
        if ($Default) { return $Default }
        if ($Required) {
            Write-Err "Value is required!"
            exit 1
        }
        return ""
    }
    return $response
}

function Ask-Number {
    param(
        [string]$Prompt,
        [int]$Default = 0,
        [int]$Min = [int]::MinValue,
        [int]$Max = [int]::MaxValue
    )
    
    $defaultText = if ($Default -ne 0) { " [$Default]" } else { "" }
    $response = Read-Host "    $Prompt$defaultText"
    
    if ([string]::IsNullOrWhiteSpace($response)) {
        return $Default
    }
    
    $number = 0
    if (-not [int]::TryParse($response, [ref]$number)) {
        Write-Err "Invalid number: $response"
        exit 1
    }
    
    if ($number -lt $Min -or $number -gt $Max) {
        Write-Err "Number must be between $Min and $Max"
        exit 1
    }
    
    return $number
}

function Ask-Path {
    param(
        [string]$Prompt,
        [string]$Default = "",
        [bool]$MustExist = $true
    )
    
    $path = Ask-String -Prompt $Prompt -Default $Default -Required $MustExist
    
    if ([string]::IsNullOrWhiteSpace($path)) { return "" }
    
    # Convert to absolute if relative
    if (-not [System.IO.Path]::IsPathRooted($path)) {
        $path = Join-Path $BaseDir $path
    }
    
    if ($MustExist -and -not (Test-Path $path)) {
        Write-Err "Path does not exist: $path"
        exit 1
    }
    
    return $path
}
