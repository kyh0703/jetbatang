<#
.SYNOPSIS
  JetBatang NF 를 현재 사용자 계정에 설치하거나 제거한다.

.DESCRIPTION
  파일 복사와 레지스트리 등록만으로는 실행 중인 세션이 글꼴을 인식하지 못한다.
  DirectWrite 는 가족 목록에는 올리면서 파일로 연결하지 못해, 그 가족을 쓰려는
  프로그램이 GetFont 에서 DWRITE_E_FILENOTFOUND(0x88985003) 를 받는다.
  그래서 AddFontResourceW 를 부르고 WM_FONTCHANGE 를 방송한다.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install-windows.ps1
  powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Uninstall
#>
[CmdletBinding()]
param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class JetBatangFontApi {
  [DllImport("gdi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern int AddFontResourceW(string file);
  [DllImport("gdi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern bool RemoveFontResourceW(string file);
  [DllImport("user32.dll", CharSet=CharSet.Auto)]
  public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint msg, IntPtr wParam,
                                                 IntPtr lParam, uint flags, uint timeout, out IntPtr result);
}
"@

# fonts/ 에 있는 것만 설치한다. 네 종만 받아도, 열여섯 종을 다 받아도 그대로 동작한다.
$faces = [ordered]@{
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
$fontDir = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
$regKey  = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
$source  = Join-Path $PSScriptRoot 'fonts'

function Broadcast-FontChange {
    $result = [IntPtr]::Zero
    # HWND_BROADCAST(0xffff), WM_FONTCHANGE(0x1D), SMTO_ABORTIFHUNG(2)
    [void][JetBatangFontApi]::SendMessageTimeout([IntPtr]0xffff, 0x1D, [IntPtr]::Zero,
                                                 [IntPtr]::Zero, 2, 3000, [ref]$result)
}

if ($Uninstall) {
    foreach ($file in $faces.Keys) {
        $path = Join-Path $fontDir $file
        if (Test-Path $path) {
            [void][JetBatangFontApi]::RemoveFontResourceW($path)
            Remove-Item $path -Force
        }
        Remove-ItemProperty -Path $regKey -Name $faces[$file] -ErrorAction SilentlyContinue
        Write-Host "  제거: $file"
    }
    Broadcast-FontChange
    Write-Host "제거 완료. 프로그램을 다시 시작하세요."
    return
}

New-Item -ItemType Directory -Path $fontDir -Force | Out-Null
$installed = @()
foreach ($file in $faces.Keys) {
    $src = Join-Path $source $file
    if (-not (Test-Path $src)) { continue }
    $path = Join-Path $fontDir $file

    # 이미 걸려 있는 판이 같은 파일이면 굳이 건드리지 않는다.
    $same = (Test-Path $path) -and ((Get-FileHash $src).Hash -eq (Get-FileHash $path).Hash)

    if (-not $same) {
        if (Test-Path $path) {
            # GDI 에 매핑된 채로는 덮어쓸 수 없다. 떼어내고 방송한 뒤 지운다.
            [void][JetBatangFontApi]::RemoveFontResourceW($path)
            Broadcast-FontChange
            for ($i = 0; $i -lt 10 -and (Test-Path $path); $i++) {
                try { Remove-Item $path -Force -ErrorAction Stop }
                catch { Start-Sleep -Milliseconds 300 }
            }
        }
        if (Test-Path $path) {
            throw "글꼴 파일이 사용 중입니다. 이 글꼴을 쓰는 프로그램을 모두 닫고 다시 실행하세요: $path"
        }
        Copy-Item $src $path -Force
    }

    $added = [JetBatangFontApi]::AddFontResourceW($path)
    if ($added -eq 0) { throw "AddFontResourceW 실패: $path" }
    New-ItemProperty -Path $regKey -Name $faces[$file] -Value $path -PropertyType String -Force | Out-Null
    $installed += $path
    Write-Host "  설치: $file"
}
if ($installed.Count -eq 0) { throw "설치할 글꼴이 없습니다. fonts/ 를 확인하세요: $source" }
Broadcast-FontChange

Add-Type -AssemblyName PresentationCore
$family = [System.Windows.Media.Fonts]::SystemFontFamilies | Where-Object { $_.Source -eq 'JetBatang NF' }
if (-not $family) { throw "설치는 됐지만 DirectWrite 가 아직 인식하지 못합니다. 로그오프 후 다시 시도하세요." }

# 가족이 들고 있는 typeface 목록으로 확인하면 안 된다. WPF 글꼴 캐시에 예전 등록이
# 남아 있으면 이미 없는 파일을 가리켜 FileNotFoundException 이 난다. 방금 넣은
# 파일을 직접 열어 본다.
foreach ($path in $installed) {
    try { $null = New-Object System.Windows.Media.GlyphTypeface ([Uri]$path) }
    catch { throw "face 를 열지 못했습니다: $path`n$($_.Exception.Message)" }
}
Write-Host "설치 완료. 터미널을 다시 시작하고 글꼴을 'JetBatang NF' 로 지정하세요."
