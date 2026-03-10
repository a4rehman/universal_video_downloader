$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\OmniStream.lnk")
$Shortcut.TargetPath = "g:\fiverr\fiverr_env\Scripts\python.exe"
$Shortcut.Arguments = "g:\fiverr\universal_downloader\app_gui.py"
$Shortcut.WorkingDirectory = "g:\fiverr\universal_downloader"
$Shortcut.Description = "Launch OmniStream Downloader"
$Shortcut.IconLocation = "shell32.dll, 164" # Download icon
$Shortcut.Save()
Write-Host "Desktop Shortcut for OmniStream Created!"
