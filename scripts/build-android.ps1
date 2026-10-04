<#
.SYNOPSIS
  Builds the P'achapp Android release APK on Windows from the WSL checkout.

.DESCRIPTION
  Mirrors <Source>\app into a Windows work directory (native Gradle on the
  Windows disk is far faster than over \\wsl.localhost), prebuilds the Android
  project, runs assembleRelease and copies the APK. The release variant is
  signed with the debug keystore by the Expo template: fine for personal use.

.PARAMETER Source   Repo root (default: the WSL checkout via \\wsl.localhost).
.PARAMETER WorkDir  Windows build directory.
.PARAMETER ApiUrl   API base URL baked into the bundle (default: .env.lan).
.PARAMETER Install  adb install -r on the USB-connected phone.
.PARAMETER Clean    Wipe WorkDir and prebuild from scratch.
.PARAMETER Abis     Native ABIs to build (default arm64-v8a, every modern phone).
#>
param(
    [string]$Source = '\\wsl.localhost\Ubuntu-22.04\home\educcio\code\pachapp',
    [string]$WorkDir = (Join-Path $env:LOCALAPPDATA 'pachapp-android'),
    [string]$ApiUrl,
    [switch]$Install,
    [switch]$Clean,
    [string]$Abis = 'arm64-v8a'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Launched from WSL the current directory is a \\wsl.localhost path, which cmd.exe rejects.
Set-Location $env:TEMP

# Call the .cmd shims: npm.ps1/npx.ps1 break under Set-StrictMode.
$npm = 'npm.cmd'
$npx = 'npx.cmd'

function Assert-Native([string]$What) {
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

function Get-Hash([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

# --- Prerequisites -----------------------------------------------------------

foreach ($tool in 'node', $npm, $npx) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool not found on PATH. Install Node.js for Windows."
    }
}

$studioJbr = 'C:\Program Files\Android\Android Studio\jbr'
if (-not ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe')))) {
    $env:JAVA_HOME = $studioJbr
}
if (-not (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe'))) {
    throw "No JDK found (JAVA_HOME=$env:JAVA_HOME). Install Android Studio or set JAVA_HOME to a JDK 17+."
}
# `java -version` writes to stderr; run it through cmd so it cannot raise.
$javaVersion = (cmd /c "`"$env:JAVA_HOME\bin\java.exe`" -version 2>&1" | Select-Object -First 1)
if ($javaVersion -notmatch '"(\d+)') { throw "Cannot read the Java version: $javaVersion" }
if ([int]$Matches[1] -lt 17) { throw "JDK 17+ required, found: $javaVersion" }

if (-not $env:ANDROID_HOME) {
    $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
}
if (-not (Test-Path $env:ANDROID_HOME)) {
    throw "Android SDK not found at $env:ANDROID_HOME. Set ANDROID_HOME."
}
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$adb = Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe'

$envLan = Join-Path $Source '.env.lan'
if (-not $ApiUrl) {
    $line = $null
    if (Test-Path $envLan) {
        $line = Get-Content $envLan | Where-Object { $_ -match '^\s*EXPO_PUBLIC_API_BASE_URL\s*=' } | Select-Object -First 1
    }
    if (-not $line) {
        throw "No -ApiUrl given and EXPO_PUBLIC_API_BASE_URL is missing from $envLan."
    }
    $ApiUrl = ($line -replace '^\s*EXPO_PUBLIC_API_BASE_URL\s*=\s*', '').Trim().Trim('"').Trim("'")
}
if ($ApiUrl -notmatch '^https?://') { throw "Invalid API URL: $ApiUrl" }

Write-Host "Source:   $Source"
Write-Host "WorkDir:  $WorkDir"
Write-Host "API URL:  $ApiUrl"
Write-Host "Node:     $(node --version) / npm $(& $npm --version)"
Write-Host "JAVA_HOME: $env:JAVA_HOME ($javaVersion)"
Write-Host "SDK:      $env:ANDROID_HOME"

# --- Mirror the app ----------------------------------------------------------

if (-not (Test-Path (Join-Path $Source 'app\package.json'))) {
    throw "$Source\app\package.json not found. Check -Source."
}
if ($Clean -and (Test-Path $WorkDir)) {
    Write-Host 'Clean: removing the work directory.'
    Remove-Item -Recurse -Force $WorkDir
}
$appDir = Join-Path $WorkDir 'app'
New-Item -ItemType Directory -Force -Path $appDir | Out-Null

# /XD also keeps /MIR from deleting the work copy's own node_modules/android.
robocopy (Join-Path $Source 'app') $appDir /MIR /NFL /NDL /NJH /NJS /NP `
    /XD node_modules .expo android ios dist web-build coverage
if ($LASTEXITCODE -gt 7) { throw "robocopy failed (exit code $LASTEXITCODE)." }
# Reset the global: a plain assignment would create a script-scoped copy that hides it.
$global:LASTEXITCODE = 0

Push-Location $appDir
try {
    # --- Dependencies --------------------------------------------------------

    $lockHash = Get-Hash 'package-lock.json'
    $lockStamp = Join-Path $WorkDir 'lock.sha256'
    $lastLock = if (Test-Path $lockStamp) { (Get-Content $lockStamp -Raw).Trim() } else { '' }
    if (-not (Test-Path 'node_modules') -or $lastLock -ne $lockHash) {
        Write-Host 'Installing dependencies (npm ci)...'
        & $npm ci
        Assert-Native 'npm ci'
        Set-Content -Path $lockStamp -Value $lockHash
    }

    # --- Prebuild ------------------------------------------------------------

    $env:EXPO_PUBLIC_API_BASE_URL = $ApiUrl
    $env:NODE_ENV = 'production'

    $configHash = (Get-Hash 'app.json') + (Get-Hash 'package.json')
    $configStamp = Join-Path $WorkDir 'prebuild.sha256'
    $lastConfig = if (Test-Path $configStamp) { (Get-Content $configStamp -Raw).Trim() } else { '' }
    $prebuildArgs = @('expo', 'prebuild', '--platform', 'android', '--no-install')
    if ($Clean -or $lastConfig -ne $configHash -or -not (Test-Path 'android')) {
        $prebuildArgs += '--clean'
    }
    Write-Host "Prebuilding: npx $($prebuildArgs -join ' ')"
    & $npx @prebuildArgs
    Assert-Native 'expo prebuild'
    Set-Content -Path $configStamp -Value $configHash

    # --- Gradle release build ------------------------------------------------

    Push-Location 'android'
    try {
        # android/ is regenerated by prebuild, so memory and ABIs go on the command line.
        # The default Gradle heap ran out of Metaspace building all four ABIs.
        .\gradlew.bat assembleRelease --max-workers=2 `
            '-Dorg.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=1g -Dfile.encoding=UTF-8' `
            "-PreactNativeArchitectures=$Abis"
        Assert-Native 'gradlew assembleRelease'
    }
    finally { Pop-Location }

    # --- Collect the APK -----------------------------------------------------

    $built = 'android\app\build\outputs\apk\release\app-release.apk'
    if (-not (Test-Path $built)) { throw "APK not found at $built." }
    $version = (Get-Content 'app.json' -Raw | ConvertFrom-Json).expo.version
    $stamp = Get-Date -Format 'yyyyMMdd-HHmm'
    $apk = Join-Path $WorkDir "pachapp-$version-$stamp.apk"
    $latest = Join-Path $WorkDir 'pachapp-latest.apk'
    Copy-Item $built $apk -Force
    Copy-Item $built $latest -Force
    $sizeMb = [math]::Round((Get-Item $apk).Length / 1MB, 1)
    Write-Host "APK: $apk ($sizeMb MB)"
    Write-Host "     $latest"
}
finally { Pop-Location }

# --- Install on the phone ----------------------------------------------------

if ($Install) {
    if (-not (Test-Path $adb)) { throw "adb not found at $adb." }
    $devices = @(& $adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice$' })
    Assert-Native 'adb devices'
    if ($devices.Count -eq 0) {
        throw 'No authorized device found. Connect the phone over USB, enable USB debugging and accept the prompt.'
    }
    if ($devices.Count -gt 1) {
        throw "More than one device connected; unplug all but one.`n$($devices -join "`n")"
    }
    & $adb install -r $latest
    Assert-Native 'adb install'
    Write-Host 'Installed on the phone.'
}
