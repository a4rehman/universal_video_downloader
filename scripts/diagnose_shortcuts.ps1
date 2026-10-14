# OmniStream Windows Desktop Shortcuts & Environment Diagnostic
# Verifies all shortcuts, target executables, scripts, and python environments.

$ErrorActionPreference = "Continue"

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "       OMNISTREAM WINDOWS SHORTCUT DIAGNOSTIC           " -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

$shell = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)

$shortcuts = @(
    "OmniStream Desktop GUI.lnk",
    "OmniStream Web App.lnk",
    "OmniStream.lnk"
)

foreach ($name in $shortcuts) {
    $lnkPath = Join-Path $desktop $name
    Write-Host "Checking: $name" -ForegroundColor Yellow
    if (Test-Path $lnkPath) {
        Write-Host "  [FOUND] at $lnkPath" -ForegroundColor Green
        try {
            $sc = $shell.CreateShortcut($lnkPath)
            Write-Host "    Target:           $($sc.TargetPath)"
            Write-Host "    Arguments:        $($sc.Arguments)"
            Write-Host "    WorkingDirectory: $($sc.WorkingDirectory)"
            Write-Host "    IconLocation:     $($sc.IconLocation)"
            
            # Check target executable
            if (Test-Path $sc.TargetPath) {
                Write-Host "    Target Executable: VALID (Exists)" -ForegroundColor Green
            } else {
                Write-Host "    Target Executable: INVALID / NOT FOUND" -ForegroundColor Red
            }

            # Check working directory
            if (Test-Path $sc.WorkingDirectory) {
                Write-Host "    Working Directory: VALID (Exists)" -ForegroundColor Green
            } else {
                Write-Host "    Working Directory: INVALID / NOT FOUND" -ForegroundColor Red
            }
        } catch {
            Write-Host "    Error reading shortcut properties: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "  [NOT FOUND] (Optional alternative name)" -ForegroundColor Gray
    }
    Write-Host ""
}

Write-Host "Checking Python Environment:" -ForegroundColor Yellow
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
Write-Host "  python.exe:  $py"
Write-Host "  pythonw.exe: $pyw"

Write-Host "`nDiagnostic completed.`n" -ForegroundColor Cyan
