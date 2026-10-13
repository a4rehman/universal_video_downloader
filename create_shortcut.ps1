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

$py = (Get-Command pythonw -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
if (-not $py) { 
    $py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue) 
}
if (-not $py) {
    $py = "pythonw.exe"
}

$ShortcutPath = Join-Path $DesktopPath "OmniStream.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $py
$appPath = Join-Path $ScriptDir "app_gui.py"
$Shortcut.Arguments = "`"$appPath`""
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "Launch OmniStream Downloader"
$Shortcut.IconLocation = "shell32.dll, 164"
$Shortcut.Save()

Write-Host "Desktop Shortcut created at: $ShortcutPath"

