# start_chrome.ps1 - launch a debuggable Chrome the agent can ride along in.
#
# It uses ./chrome-profile, NOT your real "User Data" folder: Chrome 136+ hard-blocks
# --remote-debugging-port whenever --user-data-dir is the real profile. Run ./sync_profile.ps1
# (or pass -Sync here) to copy your live cookies/sessions into chrome-profile first, so this
# window is already logged into everything you're logged into.
#
# Run:  ./start_chrome.ps1          attach to the profile as it stands
#       ./start_chrome.ps1 -Sync    re-pull your current sessions first (closes Chrome)
#
# Then leave this Chrome open and run:  python agent.py "..."

param(
    [switch]$Sync,
    [string]$SourceProfile = "Default"
)

$chrome   = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profile  = Join-Path $PSScriptRoot "chrome-profile"   # persistent, git-ignored
$port     = 9222

if ($Sync) {
    & (Join-Path $PSScriptRoot "sync_profile.ps1") -SourceProfile $SourceProfile
}

New-Item -ItemType Directory -Force -Path $profile | Out-Null

# A leftover lock from a hard kill makes Chrome silently open in your real profile instead.
foreach ($lock in "lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket") {
    Remove-Item (Join-Path $profile $lock) -Force -ErrorAction SilentlyContinue
}

Write-Host "Launching Chrome with remote debugging on http://127.0.0.1:$port"
Write-Host "Profile: $profile"

# Start-Process (not "& $chrome") so Chrome is detached: it survives this shell closing and
# doesn't block the terminal for as long as the browser is open.
Start-Process -FilePath $chrome -ArgumentList @(
    "--remote-debugging-port=$port",
    "--user-data-dir=$profile",
    "--restore-last-session",
    "https://x.com/home"
)

# Wait for the DevTools endpoint so callers know it's actually ready.
foreach ($i in 1..25) {
    try {
        $v = Invoke-RestMethod "http://127.0.0.1:$port/json/version" -TimeoutSec 2
        Write-Host "Ready: $($v.Browser)" -ForegroundColor Green
        return
    } catch { Start-Sleep -Milliseconds 600 }
}
Write-Warning "Chrome started but port $port never answered."
