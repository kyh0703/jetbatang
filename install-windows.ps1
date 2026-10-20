<#
.SYNOPSIS
  JetBatang NF 설치, 안전한 업데이트, 제거 및 백업 복원.
.DESCRIPTION
  기존 HKLM/HKCU 등록을 찾아 설치 범위를 유지한다. 처음 설치할 때만 현재
  사용자가 기본값이며 -AllUsers 는 관리자 권한이 필요하다. 두 범위에 함께
  설치돼 있거나 같은 face 가 서로 다른 파일을 가리키면 변경 없이 중단한다.

  스크립트 옆 또는 fonts\ 의 있는 face 만 설치한다 (16종/기본 4종/단일 파일).
  업데이트는 SHA256 이름의 새 파일에 등록을 연결하므로 사용 중인 파일을
  덮어쓰지 않는다. 이전 파일은 실행 중인 앱과 복원을 위해 그대로 보존한다.
  프로세스를 종료하거나 재부팅을 예약하지 않는다. 완료 후 앱을 다시 시작한다.

  변경 전 파일과 정확한 레지스트리 값/형식은 범위별 JetBatangNF\Backups 에
  SHA256 과 함께 저장한다 (사용자: LOCALAPPDATA, 전체 사용자: ProgramData).
  -Rollback 에 출력된 백업 폴더를 주면 이전 상태로 복원한다. 복원도 백업한다.
  제거 중 잠긴 파일은 등록만 제거하고 경로를 알린다. 앱을 닫은 뒤 그 파일만
  수동으로 지워도 된다. -WhatIf 는 파일/레지스트리/세션을 변경하지 않는다.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -WhatIf
  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -AllUsers
  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -Uninstall
  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -Rollback 'C:\...\Backups\...'
#>
[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [switch]$Uninstall,
    [switch]$AllUsers,
    [string]$Rollback
)

function Get-JetBatangFaces {
    return [ordered]@{
        'JetBatangNF-Thin.ttf'             = 'JetBatang NF Thin (TrueType)'
        'JetBatangNF-ThinItalic.ttf'       = 'JetBatang NF Thin Italic (TrueType)'
        'JetBatangNF-ExtraLight.ttf'       = 'JetBatang NF ExtraLight (TrueType)'
        'JetBatangNF-ExtraLightItalic.ttf' = 'JetBatang NF ExtraLight Italic (TrueType)'
        'JetBatangNF-Light.ttf'            = 'JetBatang NF Light (TrueType)'
        'JetBatangNF-LightItalic.ttf'      = 'JetBatang NF Light Italic (TrueType)'
        'JetBatangNF-Regular.ttf'          = 'JetBatang NF Regular (TrueType)'
        'JetBatangNF-Italic.ttf'           = 'JetBatang NF Italic (TrueType)'
        'JetBatangNF-Medium.ttf'           = 'JetBatang NF Medium (TrueType)'
        'JetBatangNF-MediumItalic.ttf'     = 'JetBatang NF Medium Italic (TrueType)'
        'JetBatangNF-SemiBold.ttf'         = 'JetBatang NF SemiBold (TrueType)'
        'JetBatangNF-SemiBoldItalic.ttf'   = 'JetBatang NF SemiBold Italic (TrueType)'
        'JetBatangNF-Bold.ttf'             = 'JetBatang NF Bold (TrueType)'
        'JetBatangNF-BoldItalic.ttf'       = 'JetBatang NF Bold Italic (TrueType)'
        'JetBatangNF-ExtraBold.ttf'        = 'JetBatang NF ExtraBold (TrueType)'
        'JetBatangNF-ExtraBoldItalic.ttf'  = 'JetBatang NF ExtraBold Italic (TrueType)'
    }
}

function Get-JetBatangContext {
    param([string]$SourceRoot)
    return [pscustomobject]@{
        SourceRoot = $SourceRoot
        UserFontDir = (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts')
        AllUsersFontDir = (Join-Path $env:WINDIR 'Fonts')
        UserBackupRoot = (Join-Path $env:LOCALAPPDATA 'JetBatangNF\Backups')
        AllUsersBackupRoot = (Join-Path $env:ProgramData 'JetBatangNF\Backups')
    }
}

function Test-JetBatangAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    try {
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }
    finally { $identity.Dispose() }
}

function Open-JetBatangFontRegistry {
    param([string]$Scope, [switch]$Writable)
    $hive = [Microsoft.Win32.RegistryHive]::CurrentUser
    if ($Scope -eq 'AllUsers') { $hive = [Microsoft.Win32.RegistryHive]::LocalMachine }
    $view = [Microsoft.Win32.RegistryView]::Registry32
    if ([Environment]::Is64BitOperatingSystem) { $view = [Microsoft.Win32.RegistryView]::Registry64 }
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
    try {
        $name = 'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts'
        if ($Writable) { return $base.CreateSubKey($name) }
        return $base.OpenSubKey($name, $false)
    }
    finally { $base.Dispose() }
}

function Get-JetBatangRegistryValues {
    param([string]$Scope)
    $key = Open-JetBatangFontRegistry -Scope $Scope
    if ($null -eq $key) { return }
    try {
        foreach ($name in $key.GetValueNames()) {
            [pscustomobject]@{
                Name = $name
                Value = $key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                Kind = $key.GetValueKind($name).ToString()
            }
        }
    }
    finally { $key.Dispose() }
}

function Set-JetBatangRegistryValue {
    param([string]$Scope, [string]$Name, [string]$Value, [string]$Kind)
    $key = Open-JetBatangFontRegistry -Scope $Scope -Writable
    try { $key.SetValue($Name, $Value, [Microsoft.Win32.RegistryValueKind]::$Kind) }
    finally { $key.Dispose() }
}

function Remove-JetBatangRegistryValue {
    param([string]$Scope, [string]$Name)
    $key = Open-JetBatangFontRegistry -Scope $Scope -Writable
    try { $key.DeleteValue($Name, $false) }
    finally { $key.Dispose() }
}

function Initialize-JetBatangFontApi {
    if ('JetBatangFontApi' -as [type]) { return }
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class JetBatangFontApi {
  [DllImport("gdi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern int AddFontResourceW(string file);
  [DllImport("gdi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern bool RemoveFontResourceW(string file);
  [DllImport("user32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern IntPtr SendMessageTimeoutW(IntPtr hWnd, uint msg, IntPtr wParam,
      IntPtr lParam, uint flags, uint timeout, out IntPtr result);
}
"@
}

function Add-JetBatangFontResource {
    param([string]$Path)
    Initialize-JetBatangFontApi
    return [JetBatangFontApi]::AddFontResourceW($Path)
}

function Remove-JetBatangFontResource {
    param([string]$Path)
    Initialize-JetBatangFontApi
    [void][JetBatangFontApi]::RemoveFontResourceW($Path)
}

function Send-JetBatangFontChange {
    Initialize-JetBatangFontApi
    $result = [IntPtr]::Zero
    # HWND_BROADCAST, WM_FONTCHANGE, SMTO_ABORTIFHUNG; never wait indefinitely.
    $sent = [JetBatangFontApi]::SendMessageTimeoutW([IntPtr]0xffff, 0x1D, [IntPtr]::Zero,
        [IntPtr]::Zero, 2, 3000, [ref]$result)
    if ($sent -eq [IntPtr]::Zero) {
        Write-Warning '일부 앱이 WM_FONTCHANGE 에 응답하지 않았습니다. 해당 앱을 다시 시작하세요.'
    }
}

function Test-JetBatangFontFile {
    param([string]$Path)
    # GlyphTypeface 는 폴더의 파일 목록을 프로세스 안에 캐시한다. 같은 폴더를 업데이트하면 유효한 새 파일도
    # 오래된 캐시로 검사하다 실패할 수 있으므로, 새 프로세스에서 정확한 파일을 읽고 핸들도 함께 해제한다.
    $encodedPath = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Path))
    $code = @'
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
try {
    Add-Type -AssemblyName PresentationCore
    $path = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PATH__'))
    $glyph = New-Object System.Windows.Media.GlyphTypeface ([Uri]$path)
    if (-not @($glyph.FamilyNames.Values | Where-Object { $_ -like 'JetBatang NF*' }).Count) {
        throw 'JetBatang NF 가족이 아닙니다.'
    }
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
'@
    $code = $code.Replace('__PATH__', $encodedPath)
    $executable = Join-Path $PSHOME 'powershell.exe'
    if ([IO.File]::Exists((Join-Path $PSHOME 'pwsh.exe'))) { $executable = Join-Path $PSHOME 'pwsh.exe' }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $executable
    $start.Arguments = '-NoProfile -NonInteractive -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code))
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    $start.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        [void]$stdout.GetAwaiter().GetResult()
        $detail = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "WPF 가 글꼴 파일을 열지 못했습니다: $Path`n$detail" }
    }
    finally { $process.Dispose() }
}

function Get-JetBatangHash {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function ConvertTo-JetBatangRegistration {
    param($Context, [string]$Scope, $Entry)
    $named = $Entry.Name -match '^JetBatang\s+NF(?:\s|\(|$)'
    if ($Entry.Value -isnot [string]) {
        if ($named) { throw "지원하지 않는 글꼴 등록 값: $Scope / $($Entry.Name)" }
        return
    }
    $value = [Environment]::ExpandEnvironmentVariables($Entry.Value)
    $leaf = [IO.Path]::GetFileName($value)
    if (-not $named -and $leaf -notlike 'JetBatangNF-*.ttf') { return }
    if ($Entry.Kind -notin @('String', 'ExpandString')) {
        throw "지원하지 않는 글꼴 레지스트리 형식: $($Entry.Name) / $($Entry.Kind)"
    }
    $fileFace = $null
    $nameFace = $null
    $cleanName = ($Entry.Name -replace '\s*\(TrueType\)$', '') -replace '\s', ''
    foreach ($file in (Get-JetBatangFaces).Keys) {
        $stem = [IO.Path]::GetFileNameWithoutExtension($file)
        if ($leaf -match ('^' + [regex]::Escape($stem) + '(?:[.-].+)?\.ttf$')) { $fileFace = $file }
        $display = ((Get-JetBatangFaces)[$file] -replace '\s*\(TrueType\)$', '') -replace '\s', ''
        if ($cleanName -eq $display) { $nameFace = $file }
    }
    if ($cleanName -eq 'JetBatangNF') { $nameFace = 'JetBatangNF-Regular.ttf' }
    if (-not $fileFace -or ($nameFace -and $nameFace -ne $fileFace)) {
        throw "모호한 JetBatang 등록입니다. 변경하지 않았습니다: $Scope / $($Entry.Name) = $($Entry.Value)"
    }
    $directory = $Context.UserFontDir
    if ($Scope -eq 'AllUsers') { $directory = $Context.AllUsersFontDir }
    if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $directory $value }
    return [pscustomobject]@{
        Name = $Entry.Name; Value = $Entry.Value; Kind = $Entry.Kind
        Face = $fileFace; Path = [IO.Path]::GetFullPath($value)
    }
}

function Get-JetBatangRegistrations {
    param($Context, [string]$Scope)
    $records = @(foreach ($entry in @(Get-JetBatangRegistryValues -Scope $Scope)) {
        ConvertTo-JetBatangRegistration -Context $Context -Scope $Scope -Entry $entry
    })
    foreach ($group in @($records | Group-Object Face)) {
        if (@($group.Group.Path | Select-Object -Unique).Count -gt 1) {
            throw "같은 face 가 서로 다른 파일에 등록돼 있습니다. 먼저 중복을 정리하세요: $Scope / $($group.Name)"
        }
    }
    return $records
}

function Write-JetBatangJournal {
    param([string]$Directory, $Journal)
    $path = Join-Path $Directory 'manifest.json'
    $temporary = Join-Path $Directory 'manifest.tmp'
    [IO.File]::WriteAllText($temporary, ($Journal | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($true)))
    # Windows PowerShell 5.1 은 $null 을 빈 문자열로 바인딩한다. .NET 에 실제 null 백업 경로를 넘긴다.
    if ([IO.File]::Exists($path)) { [IO.File]::Replace($temporary, $path, [System.Management.Automation.Language.NullString]::Value) }
    else { [IO.File]::Move($temporary, $path) }
}

function New-JetBatangBackup {
    param($Context, [string]$Scope, [string]$Operation, [array]$Before, [array]$After, [array]$CreatedFiles)
    $root = $Context.UserBackupRoot
    if ($Scope -eq 'AllUsers') { $root = $Context.AllUsersBackupRoot }
    $directory = Join-Path $root ((Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory((Join-Path $directory 'files'))
    $snapshot = @()
    foreach ($entry in $Before) {
        $hash = $null
        $backupFile = $null
        if ([IO.File]::Exists($entry.Path)) {
            $hash = Get-JetBatangHash $entry.Path
            $backupFile = 'files/{0:D3}.ttf' -f $snapshot.Count
            $destination = Join-Path $directory $backupFile
            [IO.File]::Copy($entry.Path, $destination, $false)
            if ((Get-JetBatangHash $destination) -ne $hash -or (Get-JetBatangHash $entry.Path) -ne $hash) {
                throw "백업 중 원본 파일이 바뀌었습니다. 설치를 중단합니다: $($entry.Path)"
            }
        }
        $snapshot += [pscustomobject]@{
            Name = $entry.Name; Value = $entry.Value; Kind = $entry.Kind
            Face = $entry.Face; Path = $entry.Path; Hash = $hash; BackupFile = $backupFile
        }
    }
    $journal = [pscustomobject]@{
        Format = 1; Scope = $Scope; Operation = $Operation; State = 'Pending'
        CreatedUtc = [DateTime]::UtcNow.ToString('o')
        Before = @($snapshot); After = @($After); CreatedFiles = @($CreatedFiles)
    }
    Write-JetBatangJournal $directory $journal
    return [pscustomobject]@{ Directory = $directory; Journal = $journal }
}

function Read-JetBatangBackup {
    param($Context, [string]$Directory)
    $directory = [IO.Path]::GetFullPath($Directory)
    $journal = [IO.File]::ReadAllText((Join-Path $directory 'manifest.json')) | ConvertFrom-Json
    if ($journal.Format -ne 1 -or $journal.Scope -notin @('CurrentUser', 'AllUsers') -or
        $journal.State -notin @('Pending', 'Committed', 'RolledBack')) {
        throw '지원하지 않거나 손상된 백업 manifest.json 입니다.'
    }
    foreach ($entry in @($journal.Before) + @($journal.After)) {
        $record = ConvertTo-JetBatangRegistration -Context $Context -Scope $journal.Scope -Entry $entry
        if (-not $record -or $record.Face -ne $entry.Face -or $record.Path -ne $entry.Path) {
            throw '백업의 레지스트리 값/파일 경로가 일치하지 않습니다.'
        }
    }
    foreach ($entry in @($journal.Before)) {
        if ($null -eq $entry.Hash) {
            if ($null -ne $entry.BackupFile) { throw '잘못된 누락 파일 백업 정보입니다.' }
            continue
        }
        if ($entry.Hash -notmatch '^[0-9a-f]{64}$' -or $entry.BackupFile -notmatch '^files/[0-9]+\.ttf$') {
            throw '잘못된 백업 파일명 또는 SHA256 입니다.'
        }
        $file = Join-Path $directory $entry.BackupFile
        if (-not [IO.File]::Exists($file) -or (Get-JetBatangHash $file) -ne $entry.Hash) {
            throw "백업 SHA256 검증 실패. 아무것도 복원하지 않았습니다: $file"
        }
    }
    # Cleanup may also involve an original versioned file recreated by rollback.
    # Bind every candidate to a validated desired registration and its exact hash.
    foreach ($file in @($journal.CreatedFiles)) {
        $targets = @($journal.After | Where-Object { $_.Path -eq $file.Path -and $_.Hash -eq $file.Hash })
        if ($file.Hash -notmatch '^[0-9a-f]{64}$' -or -not $targets.Count) {
            throw '백업에 안전하지 않은 정리 경로가 있습니다.'
        }
    }
    return $journal
}

function Assert-JetBatangRollbackState {
    param([array]$Current, $Journal)
    $names = @(@($Journal.Before.Name) + @($Journal.After.Name) | Select-Object -Unique)
    $faces = @(@($Journal.Before.Face) + @($Journal.After.Face) | Select-Object -Unique)
    foreach ($entry in $Current) {
        if ($entry.Face -in $faces -and $entry.Name -notin $names) {
            throw '백업 이후 같은 face 의 다른 등록이 생겼습니다. 현재 설치를 덮어쓰지 않습니다.'
        }
    }
    foreach ($name in $names) {
        $actual = @($Current | Where-Object { $_.Name -eq $name })
        $before = @($Journal.Before | Where-Object { $_.Name -eq $name })
        $after = @($Journal.After | Where-Object { $_.Name -eq $name })
        if (-not $actual.Count -and (-not $before.Count -or -not $after.Count)) { continue }
        $matches = @(@($before) + @($after) | Where-Object {
            $actual.Count -eq 1 -and $_.Value -ceq $actual[0].Value -and $_.Kind -eq $actual[0].Kind
        })
        if (-not $matches.Count) {
            throw "백업 이후 등록이 바뀌었습니다. 새 설치를 덮어쓰지 않습니다: $name"
        }
    }
}

function Get-JetBatangRestoreSources {
    param([string]$Directory, $Journal)
    foreach ($entry in @($Journal.Before)) {
        if ($null -eq $entry.Hash) { continue }
        if ([IO.File]::Exists($entry.Path)) {
            if ((Get-JetBatangHash $entry.Path) -ne $entry.Hash) {
                throw "이전 파일 경로에 다른 내용이 있습니다. 덮어쓰지 않습니다: $($entry.Path)"
            }
        }
        else {
            [pscustomobject]@{
                Source = (Join-Path $Directory $entry.BackupFile); Path = $entry.Path; Hash = $entry.Hash
            }
        }
    }
}

function Copy-JetBatangSources {
    param([array]$Sources)
    foreach ($file in $Sources) {
        if ([IO.File]::Exists($file.Path)) {
            if ((Get-JetBatangHash $file.Path) -ne $file.Hash) { throw "대상 파일 충돌: $($file.Path)" }
            continue
        }
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($file.Path))
        [IO.File]::Copy($file.Source, $file.Path, $false)
        if ((Get-JetBatangHash $file.Path) -ne $file.Hash) { throw "복사 후 SHA256 불일치: $($file.Path)" }
    }
}

function Set-JetBatangState {
    param([string]$Scope, [array]$Previous, [array]$Desired)
    $desiredPaths = @($Desired.Path | Select-Object -Unique)
    foreach ($path in $desiredPaths) {
        if (-not [IO.File]::Exists($path)) { continue } # Restore an originally missing registration faithfully.
        Test-JetBatangFontFile $path
        if ((Add-JetBatangFontResource $path) -eq 0) { throw "AddFontResourceW 실패: $path" }
    }
    foreach ($entry in $Desired) {
        Set-JetBatangRegistryValue -Scope $Scope -Name $entry.Name -Value $entry.Value -Kind $entry.Kind
    }
    foreach ($entry in $Previous) {
        if ($entry.Name -notin @($Desired.Name)) { Remove-JetBatangRegistryValue -Scope $Scope -Name $entry.Name }
    }
    foreach ($path in @($Previous.Path | Select-Object -Unique)) {
        if ($path -notin $desiredPaths) { Remove-JetBatangFontResource $path }
    }
    Send-JetBatangFontChange
    foreach ($path in $desiredPaths) {
        if ([IO.File]::Exists($path)) { Test-JetBatangFontFile $path }
    }
}

function Remove-JetBatangCreatedFiles {
    param($Context, [string]$Scope, [array]$Files)
    $registered = @((Get-JetBatangRegistrations -Context $Context -Scope $Scope).Path)
    foreach ($file in $Files) {
        if ($file.Path -in $registered -or -not [IO.File]::Exists($file.Path)) { continue }
        try {
            if ((Get-JetBatangHash $file.Path) -eq $file.Hash) { [IO.File]::Delete($file.Path) }
        }
        catch { Write-Warning "복구 후 사용 중인 새 파일을 보존했습니다: $($file.Path)" }
    }
}

function Invoke-JetBatangTransaction {
    param($Context, [string]$Scope, [string]$Operation, [array]$Before, [array]$After, [array]$Sources)
    $created = @($Sources | Where-Object { -not [IO.File]::Exists($_.Path) } | ForEach-Object {
        [pscustomobject]@{ Path = $_.Path; Hash = $_.Hash }
    })
    $backup = New-JetBatangBackup -Context $Context -Scope $Scope -Operation $Operation -Before $Before -After $After -CreatedFiles $created
    Write-Host "백업: $($backup.Directory)"
    try {
        Copy-JetBatangSources $Sources
        Set-JetBatangState -Scope $Scope -Previous $Before -Desired $After
        $backup.Journal.State = 'Committed'
        Write-JetBatangJournal $backup.Directory $backup.Journal
    }
    catch {
        $failure = $_.Exception.Message
        try {
            $journal = Read-JetBatangBackup -Context $Context -Directory $backup.Directory
            $restore = @(Get-JetBatangRestoreSources -Directory $backup.Directory -Journal $journal)
            Copy-JetBatangSources $restore
            Set-JetBatangState -Scope $Scope -Previous $After -Desired @($journal.Before)
            Remove-JetBatangCreatedFiles -Context $Context -Scope $Scope -Files @($journal.CreatedFiles)
            $journal.State = 'RolledBack'
            Write-JetBatangJournal $backup.Directory $journal
        }
        catch {
            throw "변경 실패: $failure`n자동 복구도 실패했습니다: $($_.Exception.Message)`n백업을 보존했습니다. 원인을 해결한 뒤 같은 권한으로 -Rollback '$($backup.Directory)' 를 실행하세요. 앱을 다시 시작하세요."
        }
        throw "변경 실패: $failure`n이전 상태로 자동 복구했습니다. 백업: $($backup.Directory)`n앱을 다시 시작한 뒤 원인을 해결하고 다시 시도하세요."
    }
    $retained = @($Before.Path | Select-Object -Unique | Where-Object { $_ -notin @($After.Path) })
    if ($Operation -eq 'Uninstall') {
        $locked = @()
        foreach ($path in $retained) {
            try { if ([IO.File]::Exists($path)) { [IO.File]::Delete($path) } }
            catch { $locked += $path; Write-Warning "등록은 제거했지만 사용 중인 파일을 보존했습니다: $path" }
        }
        $retained = $locked
    }
    elseif ($retained.Count) {
        Write-Host '이전 파일은 실행 중인 앱과 복원을 위해 보존했습니다. 백업도 자동으로 삭제하지 않습니다.'
    }
    Write-Host '완료. 글꼴을 사용하는 터미널/편집기 등 앱을 다시 시작하세요. 프로세스 종료나 재부팅은 하지 않습니다.'
    return [pscustomobject]@{ Scope = $Scope; Changed = $true; BackupPath = $backup.Directory; RetainedPaths = @($retained) }
}

function Invoke-JetBatangInstaller {
    [CmdletBinding(SupportsShouldProcess=$true)]
    param($Context, [switch]$Uninstall, [switch]$AllUsers, [string]$Rollback)
    if ($Uninstall -and $Rollback) { throw '-Uninstall 과 -Rollback 은 함께 사용할 수 없습니다.' }
    $user = @(Get-JetBatangRegistrations -Context $Context -Scope CurrentUser)
    $machine = @(Get-JetBatangRegistrations -Context $Context -Scope AllUsers)
    if ($user.Count -and $machine.Count) {
        throw 'HKLM 과 HKCU 에 모두 JetBatang NF 가 있습니다. 혼합 설치를 먼저 정리하세요. 어느 범위도 변경하지 않았습니다.'
    }
    $scope = 'CurrentUser'
    if ($machine.Count -or $AllUsers) { $scope = 'AllUsers' }
    if ($AllUsers -and $user.Count) { throw '현재 사용자 설치가 있습니다. -AllUsers 로 중복 설치하지 않습니다. 먼저 기존 설치를 제거하세요.' }
    $journal = $null
    if ($Rollback) {
        $Rollback = [IO.Path]::GetFullPath($Rollback)
        $journal = Read-JetBatangBackup -Context $Context -Directory $Rollback
        $scope = $journal.Scope
        if (($AllUsers -and $scope -ne 'AllUsers') -or ($scope -eq 'AllUsers' -and $user.Count) -or
            ($scope -eq 'CurrentUser' -and $machine.Count)) {
            throw '백업과 현재 설치 범위가 다릅니다. 다른 범위에 중복 복원하지 않습니다.'
        }
    }
    if ($scope -eq 'AllUsers' -and -not (Test-JetBatangAdministrator)) {
        throw '전체 사용자(HKLM) 설치를 유지하려면 관리자 PowerShell 에서 같은 명령을 실행하세요 (-AllUsers). 사용자 설치로 대신하지 않았습니다.'
    }
    $existing = $user
    $fontDir = $Context.UserFontDir
    if ($scope -eq 'AllUsers') { $existing = $machine; $fontDir = $Context.AllUsersFontDir }
    $before = @()
    $after = @()
    $sources = @()
    $operation = 'Install'
    if ($Rollback) {
        Assert-JetBatangRollbackState -Current $existing -Journal $journal
        $names = @(@($journal.Before.Name) + @($journal.After.Name) | Select-Object -Unique)
        $before = @($existing | Where-Object { $_.Name -in $names })
        $after = @($journal.Before)
        $sources = @(Get-JetBatangRestoreSources -Directory $Rollback -Journal $journal)
        $operation = 'Rollback'
    }
    elseif ($Uninstall) {
        $before = @($existing)
        $operation = 'Uninstall'
    }
    else {
        $faces = Get-JetBatangFaces
        foreach ($file in $faces.Keys) {
            $source = Join-Path $Context.SourceRoot $file
            if (-not [IO.File]::Exists($source)) { $source = Join-Path (Join-Path $Context.SourceRoot 'fonts') $file }
            if (-not [IO.File]::Exists($source)) { continue }
            Test-JetBatangFontFile $source
            $hash = Get-JetBatangHash $source
            $previous = @($existing | Where-Object { $_.Face -eq $file })
            $before += $previous
            $path = Join-Path $fontDir ([IO.Path]::GetFileNameWithoutExtension($file) + '.sha256-' + $hash + '.ttf')
            $same = $previous.Count -and [IO.File]::Exists($previous[0].Path) -and (Get-JetBatangHash $previous[0].Path) -eq $hash
            if ($same) { $path = $previous[0].Path }
            if ([IO.File]::Exists($path)) {
                if ((Get-JetBatangHash $path) -ne $hash) { throw "같은 SHA256 파일명에 다른 내용이 있습니다. 덮어쓰지 않습니다: $path" }
            }
            else { $sources += [pscustomobject]@{ Source = $source; Path = $path; Hash = $hash } }
            if ($previous.Count) {
                foreach ($entry in $previous) {
                    $value = $path
                    if ($same) { $value = $entry.Value }
                    $after += [pscustomobject]@{ Name = $entry.Name; Value = $value; Kind = $entry.Kind; Face = $file; Path = $path; Hash = $hash }
                }
            }
            else {
                $after += [pscustomobject]@{ Name = $faces[$file]; Value = $path; Kind = 'String'; Face = $file; Path = $path; Hash = $hash }
            }
        }
        if (-not $after.Count) {
            throw "설치할 글꼴이 없습니다. JetBatangNF-*.ttf 를 스크립트 옆이나 fonts\ 에 두세요: $($Context.SourceRoot)"
        }
    }
    $changed = $sources.Count -gt 0 -or $before.Count -ne $after.Count
    foreach ($entry in $after) {
        if (-not @($before | Where-Object { $_.Name -eq $entry.Name -and $_.Value -ceq $entry.Value -and $_.Kind -eq $entry.Kind }).Count) { $changed = $true }
    }
    if (-not $changed) {
        Write-Host '변경할 항목이 없습니다. 기존 설치 범위를 유지했습니다.'
        return [pscustomobject]@{ Scope = $scope; Changed = $false; BackupPath = $null; RetainedPaths = @() }
    }
    if (-not $PSCmdlet.ShouldProcess("JetBatang NF / $scope / $($before.Count) -> $($after.Count) registrations", "$operation (backup + SHA256)")) {
        return [pscustomobject]@{ Scope = $scope; Changed = $false; BackupPath = $null; RetainedPaths = @() }
    }
    return Invoke-JetBatangTransaction -Context $Context -Scope $scope -Operation $operation -Before $before -After $after -Sources $sources
}

# Dot-sourcing exposes functions without touching fonts, registry or the session.
if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    try {
        $context = Get-JetBatangContext -SourceRoot $PSScriptRoot
        $null = Invoke-JetBatangInstaller -Context $context -Uninstall:$Uninstall -AllUsers:$AllUsers -Rollback $Rollback -WhatIf:$WhatIfPreference
    }
    catch { Write-Error $_; exit 1 }
}
