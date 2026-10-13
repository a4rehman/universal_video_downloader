$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)

if ($PSScriptRoot) { 
    $ScriptDir = $PSScriptRoot 
} else { 
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition 
}
if (-not $ScriptDir) {
    $ScriptDir = "a:\universal_video_downloader-main"
}

# 1. Create Shortcut for Streamlit Silent Launcher
$StreamlitLnkPath = Join-Path $DesktopPath "OmniStream Web App.lnk"
$StreamlitShortcut = $WshShell.CreateShortcut($StreamlitLnkPath)
$vbsPath = Join-Path $ScriptDir "run_streamlit.vbs"
$StreamlitShortcut.TargetPath = "wscript.exe"
$StreamlitShortcut.Arguments = "`"$vbsPath`""
$StreamlitShortcut.WorkingDirectory = $ScriptDir
$StreamlitShortcut.Description = "Launch OmniStream Web App (Silent Mode)"
$StreamlitShortcut.IconLocation = "shell32.dll, 14"
$StreamlitShortcut.Save()

# 2. Create Shortcut for Desktop GUI App
$DesktopLnkPath = Join-Path $DesktopPath "OmniStream Desktop GUI.lnk"
$DesktopShortcut = $WshShell.CreateShortcut($DesktopLnkPath)
$guiPath = Join-Path $ScriptDir "app_gui.py"
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
if (-not $pyw) { 
    $pyw = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue) 
}
if (-not $pyw) { 
    $pyw = "pythonw.exe" 
}
$DesktopShortcut.TargetPath = $pyw
$DesktopShortcut.Arguments = "`"$guiPath`""
$DesktopShortcut.WorkingDirectory = $ScriptDir
$DesktopShortcut.Description = "Launch OmniStream Desktop App"
$DesktopShortcut.IconLocation = "shell32.dll, 164"
$DesktopShortcut.Save()

Write-Host "Desktop shortcuts created successfully at: $DesktopPath"

