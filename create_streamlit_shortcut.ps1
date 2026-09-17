$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop")

if ($PSScriptRoot) { $ScriptDir = $PSScriptRoot } else { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition }

# Create Shortcut for Streamlit Silent Launcher
$StreamlitShortcut = $WshShell.CreateShortcut("$DesktopPath\OmniStream Web App.lnk")
$vbsPath = Join-Path $ScriptDir "run_streamlit.vbs"
$StreamlitShortcut.TargetPath = "wscript.exe"
$StreamlitShortcut.Arguments = "`"$vbsPath`""
$StreamlitShortcut.WorkingDirectory = $ScriptDir
$StreamlitShortcut.Description = "Launch OmniStream Web App (Silent Mode)"
$StreamlitShortcut.IconLocation = "shell32.dll, 14"
$StreamlitShortcut.Save()

# Create Shortcut for Desktop GUI App
$DesktopShortcut = $WshShell.CreateShortcut("$DesktopPath\OmniStream Desktop GUI.lnk")
$guiPath = Join-Path $ScriptDir "app_gui.py"
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
if (-not $pyw) { $pyw = "pythonw.exe" }
$DesktopShortcut.TargetPath = $pyw
$DesktopShortcut.Arguments = "`"$guiPath`""
$DesktopShortcut.WorkingDirectory = $ScriptDir
$DesktopShortcut.Description = "Launch OmniStream Desktop App"
$DesktopShortcut.IconLocation = "shell32.dll, 164"
$DesktopShortcut.Save()

Write-Host "Desktop shortcuts created successfully!"
