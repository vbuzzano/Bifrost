# Load .env file into environment
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^([^#=]+)=(.*)$') {
            Set-Item "env:$($matches[1])" $matches[2]
        }
    }
}

# add directory script top path
$env:PATH = "$pwd\scripts;$env:PATH;"
