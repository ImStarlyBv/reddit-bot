# start_chrome.ps1 — launch YOUR Chrome with remote debugging so the agent can ride along.
#
# This opens a normal Chrome window you browse in. Log into Google/Reddit here ONCE (the profile
# below persists your session). The agent then attaches to THIS window and opens its work in a new
# tab — exactly the "it uses the browser I'm already in" behavior.
#
# Run:  ./start_chrome.ps1     then leave this Chrome open and run:  python agent.py "..."

$chrome   = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profile  = Join-Path $PSScriptRoot "chrome-profile"   # persistent, git-ignored
$port     = 9222

New-Item -ItemType Directory -Force -Path $profile | Out-Null

Write-Host "Launching Chrome with remote debugging on http://127.0.0.1:$port"
Write-Host "Profile: $profile"
Write-Host "Log into Google + Reddit in this window (once). Leave it open, then run agent.py."

& $chrome `
    "--remote-debugging-port=$port" `
    "--user-data-dir=$profile" `
    "https://www.reddit.com"
