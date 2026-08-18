# sync_profile.ps1 - copy the session data (cookies, logins, tokens) out of YOUR real Chrome
# profile into the agent's chrome-profile, so the agent rides your existing sessions.
#
# Why the copy? Chrome 136+ refuses --remote-debugging-port when --user-data-dir is the real
# "User Data" folder. A copy is the only supported way to get a debuggable, logged-in profile.
# Encryption is fine: same Windows user + same machine + same chrome.exe path, so Chrome
# decrypts the copied cookies itself.
#
# Chrome MUST be fully closed (the cookie DB is locked while it runs).
#
# Run:  ./sync_profile.ps1            (then ./start_chrome.ps1)
#       ./sync_profile.ps1 -Full      (mirror the whole profile - slower, ~GBs)
#       ./sync_profile.ps1 -SourceProfile "Profile 1"

param(
    [string]$SourceProfile = "Default",
    [switch]$Full,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$src  = Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data"
$dst  = Join-Path $PSScriptRoot "chrome-profile"

if (-not (Test-Path (Join-Path $src $SourceProfile))) {
    throw "Source profile not found: $(Join-Path $src $SourceProfile)"
}

# robocopy reports 0-7 as success (bits mean "copied", "extras removed", ...) and only
# 8+ as a real failure. Left unhandled it also leaks out as this script's exit code.
function Invoke-Mirror($from, $to, $extraArgs) {
    robocopy $from $to /MIR /R:1 /W:1 /NFL /NDL /NJH /NJS @extraArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE) on $from" }
    $global:LASTEXITCODE = 0
}

# 1. Chrome must be closed or the SQLite files are locked and you get a half-copied profile.
$running = Get-Process chrome -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Chrome is running ($($running.Count) processes)." -ForegroundColor Yellow
    if (-not $Force) {
        $answer = Read-Host "Close all Chrome windows now? (y/N)"
        if ($answer -ne "y") { throw "Aborted. Close Chrome and re-run." }
    }
    # Graceful first: a forced kill leaves a dirty cookie DB and the
    # "Chrome didn't shut down correctly" nag on your next launch.
    $running | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    Start-Sleep -Seconds 3
    $left = Get-Process chrome -ErrorAction SilentlyContinue
    if ($left) { $left | Stop-Process -Force; Start-Sleep -Seconds 2 }
}

New-Item -ItemType Directory -Force -Path (Join-Path $dst "Default") | Out-Null

# 2. Back up whatever session the agent profile already had.
$oldCookies = Join-Path $dst "Default\Network\Cookies"
if (Test-Path $oldCookies) {
    Copy-Item $oldCookies "$oldCookies.bak" -Force
    Write-Host "Backed up previous agent cookies -> Default\Network\Cookies.bak"
}

if ($Full) {
    Write-Host "Full mirror of '$SourceProfile' (this takes a while)..."
    Invoke-Mirror $src $dst @(
        "/XD", "Crashpad", "BrowserMetrics", "GrShaderCache", "ShaderCache",
        "/XF", "lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket")
} else {
    # Local State holds the encrypted master key for the cookie DB - useless without it.
    Copy-Item (Join-Path $src "Local State") (Join-Path $dst "Local State") -Force

    # Files: everything that actually carries a session.
    $files = @(
        "Network\Cookies",          # the sessions themselves
        "Network\Trust Tokens",
        "Login Data",               # saved passwords, for re-auth prompts
        "Login Data For Account",
        "Web Data",                 # autofill
        "Preferences",              # signed-in Chrome identity, per-site settings
        "Secure Preferences",
        "Affiliation Database"
    )
    foreach ($f in $files) {
        $from = Join-Path $src "$SourceProfile\$f"
        if (Test-Path $from) {
            $to = Join-Path $dst "Default\$f"
            New-Item -ItemType Directory -Force -Path (Split-Path $to) | Out-Null
            Copy-Item $from $to -Force
            Write-Host "  + $f"
        }
    }

    # Dirs: many sites (Reddit, Google) keep auth tokens in localStorage / IndexedDB,
    # not only in cookies. Without these you look logged out even with valid cookies.
    $dirs = @("Local Storage", "Session Storage", "IndexedDB", "Service Worker\Database")
    foreach ($d in $dirs) {
        $from = Join-Path $src "$SourceProfile\$d"
        if (Test-Path $from) {
            Invoke-Mirror $from (Join-Path $dst "Default\$d") @()
            Write-Host "  + $d\"
        }
    }
}

Write-Host ""
Write-Host "Synced '$SourceProfile' -> chrome-profile" -ForegroundColor Green
Write-Host "Next: ./start_chrome.ps1   (leave that window open, then run python agent.py)"

exit 0
