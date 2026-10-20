param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$Fixtures,
    [Parameter(Mandatory=$true)][string]$Scenario
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)

# Load only the production functions, never its command-line entry point. This also
# makes an old/unsafe installer fail safely instead of touching a real installation.
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Installer, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
foreach ($definition in $ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Parent -is [System.Management.Automation.Language.NamedBlockAst]
}, $false)) {
    . ([scriptblock]::Create($definition.Extent.Text))
}

# These are the only system boundaries replaced. File IO, SHA256, WPF validation,
# installer decisions, backup journals and restoration execute the real code.
$script:Registry = @{ CurrentUser = @{}; AllUsers = @{} }
$script:Elevated = $true
$script:Broadcasts = 0
$script:Resources = @{}
$script:FailName = $null
function Get-JetBatangRegistryValues {
    param([string]$Scope)
    foreach ($name in @($script:Registry[$Scope].Keys)) {
        $record = $script:Registry[$Scope][$name]
        [pscustomobject]@{ Name = $name; Value = $record.Value; Kind = $record.Kind }
    }
}
function Set-JetBatangRegistryValue {
    param([string]$Scope, [string]$Name, [string]$Value, [string]$Kind)
    if ($script:FailName -eq $Name) {
        $script:FailName = $null
        throw 'Simulated registry write denied after a previous write succeeded'
    }
    $script:Registry[$Scope][$Name] = [pscustomobject]@{ Value = $Value; Kind = $Kind }
}
function Remove-JetBatangRegistryValue {
    param([string]$Scope, [string]$Name)
    $script:Registry[$Scope].Remove($Name)
}
function Test-JetBatangAdministrator { return $script:Elevated }
function Add-JetBatangFontResource {
    param([string]$Path)
    if (-not [IO.File]::Exists($Path)) { throw "Missing resource: $Path" }
    $script:Resources[$Path] = $true
    return 1
}
function Remove-JetBatangFontResource {
    param([string]$Path)
    $script:Resources.Remove($Path)
}
function Send-JetBatangFontChange { $script:Broadcasts++ }
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "Assertion failed: $Message" }
}
function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -cne $Expected) { throw "Assertion failed: $Message; expected <$Expected>, got <$Actual>" }
}
function Assert-Fails {
    param([scriptblock]$Action, [string]$Message)
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert-True $failed $Message
}
function Copy-Fixture {
    param([string]$Version, [string]$Destination)
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Destination))
    $face = 'Regular'
    foreach ($file in (Get-JetBatangFaces).Keys) {
        $stem = [IO.Path]::GetFileNameWithoutExtension($file)
        if ([IO.Path]::GetFileName($Destination) -match ('^' + [regex]::Escape($stem) + '(?:[.-].+)?\.ttf$')) {
            $face = $stem.Substring('JetBatangNF-'.Length)
            break
        }
    }
    [IO.File]::Copy((Join-Path $Fixtures "$Version-$face.ttf"), $Destination, $true)
}
function Read-Journal {
    param([string]$BackupPath)
    return ([IO.File]::ReadAllText((Join-Path $BackupPath 'manifest.json')) | ConvertFrom-Json)
}
function Assert-NoBackups {
    Assert-True (-not [IO.Directory]::Exists($ctx.UserBackupRoot)) 'no per-user backup should be written'
    Assert-True (-not [IO.Directory]::Exists($ctx.AllUsersBackupRoot)) 'no all-users backup should be written'
}
function Register-Old {
    param([string]$Scope = 'AllUsers', [string]$Face = 'Regular', [string]$Name = 'JetBatang NF (TrueType)')
    $directory = $ctx.AllUsersFontDir
    if ($Scope -eq 'CurrentUser') { $directory = $ctx.UserFontDir }
    $path = Join-Path $directory "JetBatangNF-$Face.local-1.7.0-4bfee919.ttf"
    Copy-Fixture 'old' $path
    Set-JetBatangRegistryValue $Scope $Name $path 'String'
    return $path
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('JetBatang [격리] ' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$ctx = [pscustomobject]@{
    SourceRoot = (Join-Path $root '패키지 [1]')
    UserFontDir = (Join-Path $root '사용자 [Fonts]')
    AllUsersFontDir = (Join-Path $root '전체 [Fonts]')
    UserBackupRoot = (Join-Path $root '사용자 [Backups]')
    AllUsersBackupRoot = (Join-Path $root '전체 [Backups]')
}
[void][IO.Directory]::CreateDirectory($ctx.SourceRoot)
Copy-Fixture 'new' (Join-Path $ctx.SourceRoot 'JetBatangNF-Regular.ttf')
$lock = $null
try {
    switch ($Scenario) {
        'locked-update' {
            $old = Register-Old
            $oldHash = (Get-FileHash -LiteralPath $old).Hash
            $lock = [IO.File]::Open($old, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
            $result = Invoke-JetBatangInstaller -Context $ctx
            Assert-Equal $result.Scope 'AllUsers' 'auto-detected machine installation'
            Assert-Equal $script:Registry.CurrentUser.Count 0 'no per-user duplicate'
            Assert-Equal $script:Registry.AllUsers.Count 1 'same exact registry identity'
            $path = $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value
            Assert-True ($path -ne $old) 'locked file is replaced through a unique registration path'
            Assert-Equal (Get-FileHash -LiteralPath $path).Hash (Get-FileHash -LiteralPath (Join-Path $Fixtures 'new.ttf')).Hash 'updated bytes'
            Assert-Equal (Get-FileHash -LiteralPath $old).Hash $oldHash 'locked original remains unchanged'
            $journal = Read-Journal $result.BackupPath
            Assert-Equal $journal.Before[0].Name 'JetBatang NF (TrueType)' 'backup preserves registry identity'
            Assert-Equal (Get-FileHash -LiteralPath (Join-Path $result.BackupPath $journal.Before[0].BackupFile)).Hash.ToLowerInvariant() $journal.Before[0].Hash 'backup verified by SHA256'
            Assert-True ($script:Broadcasts -gt 0) 'font change was broadcast'
            Assert-True $script:Resources.ContainsKey($path) 'new file registered with session font API'
        }
        'rollback' {
            $old = Register-Old
            $name = 'JetBatang NF (TrueType)'
            $script:Registry.AllUsers[$name].Kind = 'ExpandString'
            $hash = (Get-FileHash -LiteralPath $old).Hash
            $update = Invoke-JetBatangInstaller -Context $ctx
            [IO.File]::Delete($old)
            $restored = Invoke-JetBatangInstaller -Context $ctx -Rollback $update.BackupPath
            Assert-Equal $script:Registry.AllUsers[$name].Value $old 'exact original path restored'
            Assert-Equal $script:Registry.AllUsers[$name].Kind 'ExpandString' 'registry kind restored'
            Assert-Equal (Get-FileHash -LiteralPath $old).Hash $hash 'missing original restored from checksum-backed copy'
            Assert-True ([IO.File]::Exists((Join-Path $restored.BackupPath 'manifest.json'))) 'rollback itself is backed up'
            Assert-Equal $script:Registry.CurrentUser.Count 0 'rollback preserves scope'
            $newPath = (Read-Journal $update.BackupPath).After[0].Value
            $null = Invoke-JetBatangInstaller -Context $ctx -Rollback $restored.BackupPath
            Assert-Equal $script:Registry.AllUsers[$name].Value $newPath 'rollback backup can itself be restored'
        }
        'uninstall-locked' {
            $old = Register-Old
            $unrelated = Join-Path $ctx.AllUsersFontDir 'JetBatangNF-Regular.ttf'
            Copy-Fixture 'new' $unrelated
            $lock = [IO.File]::Open($old, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
            $removed = Invoke-JetBatangInstaller -Context $ctx -Uninstall
            Assert-Equal $script:Registry.AllUsers.Count 0 'actual identity removed despite locked file'
            Assert-True ([IO.File]::Exists($old)) 'locked registered file is retained safely'
            Assert-True ([IO.File]::Exists($unrelated)) 'unregistered base filename is not guessed/deleted'
            Assert-True (@($removed.RetainedPaths) -contains $old) 'locked file is reported'
            $null = Invoke-JetBatangInstaller -Context $ctx -Rollback $removed.BackupPath
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $old 'uninstall is reversible'
        }
        'mixed-scope' {
            $null = Register-Old
            $null = Register-Old -Scope CurrentUser
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx } 'mixed scope must not mutate either scope'
            Assert-Equal $script:Registry.AllUsers.Count 1 'machine registration unchanged'
            Assert-Equal $script:Registry.CurrentUser.Count 1 'user registration unchanged'
            Assert-NoBackups
        }
        'not-elevated' {
            $old = Register-Old
            $script:Elevated = $false
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx } 'machine upgrade requires elevation'
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx -AllUsers -Uninstall } 'machine uninstall requires elevation'
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $old 'machine registration unchanged'
            Assert-Equal $script:Registry.CurrentUser.Count 0 'never falls back to user installation'
            Assert-NoBackups
        }
        'explicit-all-users' {
            $result = Invoke-JetBatangInstaller -Context $ctx -AllUsers
            Assert-Equal $result.Scope 'AllUsers' 'explicit machine install'
            Assert-Equal $script:Registry.AllUsers.Count 1 'new machine registration'
            Assert-Equal $script:Registry.CurrentUser.Count 0 'no user registration'
            $script:Registry.AllUsers.Clear()
            $null = Register-Old -Scope CurrentUser
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx -AllUsers } 'explicit scope cannot duplicate an existing user font'
        }
        'subsets' {
            $sets = @(@('Regular'), @('Regular', 'Bold', 'Italic', 'BoldItalic'), @(
                'Thin', 'ThinItalic', 'ExtraLight', 'ExtraLightItalic', 'Light', 'LightItalic',
                'Regular', 'Italic', 'Medium', 'MediumItalic', 'SemiBold', 'SemiBoldItalic',
                'Bold', 'BoldItalic', 'ExtraBold', 'ExtraBoldItalic'))
            foreach ($faces in $sets) {
                $script:Registry.CurrentUser.Clear()
                foreach ($file in [IO.Directory]::GetFiles($ctx.SourceRoot, '*.ttf')) { [IO.File]::Delete($file) }
                # Repository-layout fonts/ and ZIP-layout adjacent files are both supported.
                $directory = $ctx.SourceRoot
                if ($faces.Count -eq 4) { $directory = Join-Path $ctx.SourceRoot 'fonts' }
                foreach ($face in $faces) { Copy-Fixture 'new' (Join-Path $directory "JetBatangNF-$face.ttf") }
                $fileCount = [IO.Directory]::GetFiles($root, '*', [IO.SearchOption]::AllDirectories).Count
                $broadcastCountBefore = $script:Broadcasts
                $resourceCountBefore = $script:Resources.Count
                $preview = Invoke-JetBatangInstaller -Context $ctx -WhatIf
                Assert-Equal $script:Registry.CurrentUser.Count 0 'WhatIf cannot install fonts'
                Assert-Equal ([IO.Directory]::GetFiles($root, '*', [IO.SearchOption]::AllDirectories).Count) $fileCount 'WhatIf cannot copy fonts or create backups'
                Assert-Equal $script:Broadcasts $broadcastCountBefore 'WhatIf cannot broadcast'
                Assert-Equal $script:Resources.Count $resourceCountBefore 'WhatIf cannot load session fonts'
                $result = Invoke-JetBatangInstaller -Context $ctx
                Assert-Equal $script:Registry.CurrentUser.Count $faces.Count 'all and only packaged faces installed'
                Assert-Equal $script:Registry.AllUsers.Count 0 'fresh default remains per-user'
                $null = Invoke-JetBatangInstaller -Context $ctx -Uninstall
                Assert-Equal $script:Registry.CurrentUser.Count 0 'subset uninstall works without package assumptions'
                $nested = Join-Path $ctx.SourceRoot 'fonts'
                if ([IO.Directory]::Exists($nested)) { [IO.Directory]::Delete($nested, $true) }
            }
        }
        'partial-failure' {
            $old = Register-Old
            $italic = Register-Old -Face Italic -Name 'JetBatang NF Italic (TrueType)'
            Copy-Fixture 'new' (Join-Path $ctx.SourceRoot 'JetBatangNF-Italic.ttf')
            $script:FailName = 'JetBatang NF Italic (TrueType)'
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx } 'registry failure must be reported'
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $old 'earlier successful registry write rolled back'
            Assert-Equal $script:Registry.AllUsers['JetBatang NF Italic (TrueType)'].Value $italic 'failing face unchanged'
            Assert-Equal $script:Registry.CurrentUser.Count 0 'failure does not leak per-user install'
            Assert-Equal ([IO.Directory]::GetFiles($ctx.AllUsersFontDir, '*.ttf')).Count 2 'staged new files cleaned after automatic rollback'
            $backups = [IO.Directory]::GetDirectories($ctx.AllUsersBackupRoot)
            Assert-Equal $backups.Count 1 'one usable recovery backup'
            Assert-Equal (Read-Journal $backups[0]).State 'RolledBack' 'journal records automatic recovery'
        }
        'invalid-font' {
            [IO.File]::WriteAllText((Join-Path $ctx.SourceRoot 'JetBatangNF-Regular.ttf'), 'not a font')
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx } 'invalid WPF font must be rejected'
            Assert-Equal $script:Registry.CurrentUser.Count 0 'invalid file not registered'
            Assert-NoBackups
        }
        'tampered-backup' {
            $old = Register-Old
            $update = Invoke-JetBatangInstaller -Context $ctx
            $journal = Read-Journal $update.BackupPath
            $newPath = $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value
            [IO.File]::WriteAllText((Join-Path $update.BackupPath $journal.Before[0].BackupFile), 'tampered')
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx -Rollback $update.BackupPath } 'tampered bytes cannot be restored'
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $newPath 'corrupt backup does not change current state'
        }
        'ambiguous' {
            $old = Register-Old
            $other = Join-Path $ctx.AllUsersFontDir 'JetBatangNF-Regular.other-hash.ttf'
            Copy-Fixture 'new' $other
            Set-JetBatangRegistryValue AllUsers 'JetBatang NF Regular (TrueType)' $other String
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx } 'different files for one face are ambiguous'
            Assert-NoBackups
        }
        'unchanged' {
            $old = Register-Old
            Copy-Fixture 'old' (Join-Path $ctx.SourceRoot 'JetBatangNF-Regular.ttf')
            $result = Invoke-JetBatangInstaller -Context $ctx
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $old 'matching installed file path is reused'
            Assert-True (-not $result.Changed) 'matching install reports no changes'
            Assert-NoBackups
        }
        'relative-aliases' {
            $old = Register-Old
            $leaf = [IO.Path]::GetFileName($old)
            Set-JetBatangRegistryValue AllUsers 'JetBatang NF (TrueType)' $leaf String
            Set-JetBatangRegistryValue AllUsers 'JetBatang NF Regular (TrueType)' $leaf ExpandString
            $updated = Invoke-JetBatangInstaller -Context $ctx
            Assert-Equal $script:Registry.AllUsers.Count 2 'exact aliases retained without a third canonical entry'
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $script:Registry.AllUsers['JetBatang NF Regular (TrueType)'].Value 'both aliases repointed together'
            $null = Invoke-JetBatangInstaller -Context $ctx -Rollback $updated.BackupPath
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $leaf 'relative registry filename restored exactly'
            Assert-Equal $script:Registry.AllUsers['JetBatang NF Regular (TrueType)'].Kind 'ExpandString' 'alias kind restored'
        }
        'rollback-drift' {
            $null = Register-Old
            $updated = Invoke-JetBatangInstaller -Context $ctx
            $external = Join-Path $ctx.AllUsersFontDir 'JetBatangNF-Regular.manual-3.ttf'
            Copy-Fixture 'old' $external
            Set-JetBatangRegistryValue AllUsers 'JetBatang NF (TrueType)' $external String
            Assert-Fails { Invoke-JetBatangInstaller -Context $ctx -Rollback $updated.BackupPath } 'rollback must not overwrite a later external update'
            Assert-Equal $script:Registry.AllUsers['JetBatang NF (TrueType)'].Value $external 'later registration unchanged'
            Assert-Equal ([IO.Directory]::GetDirectories($ctx.AllUsersBackupRoot).Count) 1 'rejected rollback makes no new backup'
        }
        default { throw "Unknown scenario: $Scenario" }
    }
}
finally {
    if ($null -ne $lock) { $lock.Dispose() }
    if ([IO.Directory]::Exists($root)) { [IO.Directory]::Delete($root, $true) }
}
