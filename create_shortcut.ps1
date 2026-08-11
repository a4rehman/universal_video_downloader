$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\OmniStream.lnk")

# Determine script directory (works when the script is double-clicked or run from PowerShell)
if ($PSScriptRoot) { $ScriptDir = $PSScriptRoot } else { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition }

# Find pythonw or fallback to python
$py = (Get-Command pythonw -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
if (-not $py) { $py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue) }
if (-not $py) {
	Write-Host "Python not found in PATH. Please ensure Python is installed and pythonw/python is available in PATH." -ForegroundColor Yellow
	exit 1
}

$Shortcut.TargetPath = $py
$appPath = Join-Path $ScriptDir "app_gui.py"
$Shortcut.Arguments = "`"$appPath`""
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "Launch OmniStream Downloader"
$Shortcut.IconLocation = "shell32.dll, 164" # Download icon
$Shortcut.Save()
Write-Host "Desktop Shortcut for OmniStream Created!"
