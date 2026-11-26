# build-setup.ps1 — empaqueta el bundle onedir de CoreFrame en UN solo .exe distribuible.
#
# Pasos: compila el stub C# -> comprime el bundle -> pega comprimido + trailer al final
# del stub. El resultado es el fichero que se descarga el usuario: al ejecutarlo por
# primera vez suelta el bundle en <Documentos>\CoreFrame\bin\host y arranca; a partir de
# ahi cada arranque es directo (no se vuelve a extraer).
#
#   .\build-setup.ps1                      # fuente = bundle desplegado, salida = dist\CoreFrame.exe
#   .\build-setup.ps1 -Source "...\dist\CoreFrame-onedir"
#   .\build-setup.ps1 -PayloadFrom "...\CoreFrame.exe"   # reusa el payload ya empaquetado
#
# -PayloadFrom sirve para reconstruir el lanzador (icono, version, etc.) SIN cambiar el
# payload: al salir identico, el host.stamp de quien lo tenga instalado sigue cuadrando y
# no se le obliga a re-extraer los 82 MB. El icono se toma de CoreFrame.ico (el mismo que
# usa PyInstaller en los dos specs).
param(
    [string]$Source = 'E:\Documentos\CoreFrame\bin\host',
    [string]$Out,
    [string]$PayloadFrom,
    [switch]$SkipCompile
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = 'E:\Programming\CoreFrame'
$launcherDir = Join-Path $root 'launcher'
$stubExe = Join-Path $launcherDir 'CoreFrameStub.exe'
if (-not $Out) { $Out = Join-Path $root 'dist\CoreFrame.exe' }

$MARKER = [byte[]]@(0xC0, 0xFF, 0xEE, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD)
$TRAILER = 40

if ($PayloadFrom) {
    if (-not (Test-Path $PayloadFrom)) { throw "no existe -PayloadFrom: $PayloadFrom" }
} else {
    if (-not (Test-Path $Source)) { throw "no existe la fuente: $Source" }
    if (-not (Test-Path (Join-Path $Source 'CoreFrame.exe'))) { throw "$Source no tiene CoreFrame.exe; no parece un bundle onedir" }
}

# --- 1. stub C# (con icono) ----------------------------------------------------
if (-not $SkipCompile) {
    $csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    if (-not (Test-Path $csc)) { $csc = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe' }
    if (-not (Test-Path $csc)) { throw "no encuentro csc.exe de .NET Framework 4" }

    $iconArg = @()
    $icon = Join-Path $root 'CoreFrame.ico'
    if (Test-Path $icon) { $iconArg = @('/win32icon:' + $icon) }
    else { "aviso: no encuentro $icon -> el lanzador saldra sin icono" }

    "compilando stub con $csc"
    & $csc /nologo /target:winexe /optimize+ /platform:anycpu `
        /r:System.Windows.Forms.dll /r:System.Drawing.dll `
        /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll `
        @iconArg `
        /out:"$stubExe" (Join-Path $launcherDir 'launcher.cs')
    if ($LASTEXITCODE -ne 0) { throw "csc fallo ($LASTEXITCODE)" }
}
if (-not (Test-Path $stubExe)) { throw "falta el stub: $stubExe" }
$stubBytes = [IO.File]::ReadAllBytes($stubExe)
"stub            : {0:N0} bytes con icono: {1}" -f $stubBytes.Length, (Test-Path (Join-Path $root 'CoreFrame.ico'))

# --- 2. payload: reutilizado o comprimido ahora --------------------------------
$reuseHash = $null
$t0 = Get-Date
if ($PayloadFrom) {
    $prev = [IO.File]::ReadAllBytes($PayloadFrom)
    if ($prev.Length -lt $TRAILER) { throw "$PayloadFrom es demasiado pequeno para llevar trailer" }
    $tl = $prev.Length - $TRAILER
    for ($i = 0; $i -lt 16; $i++) { if ($prev[$tl + 24 + $i] -ne $MARKER[$i]) { throw "firma invalida en $PayloadFrom" } }
    $len = [BitConverter]::ToInt64($prev, $tl)
    if ($len -le 0 -or $len -gt $tl) { throw "longitud invalida en $PayloadFrom ($len)" }
    $reuseHash = New-Object byte[] 16
    [Array]::Copy($prev, $tl + 8, $reuseHash, 0, 16)
    $zipBytes = New-Object byte[] $len
    [Array]::Copy($prev, $tl - $len, $zipBytes, 0, $len)
    "payload         : {0:N1} MB REUTILIZADO de {1}" -f ($zipBytes.Length/1MB), (Split-Path $PayloadFrom -Leaf)
    "                  (mismo payload = el stamp instalado sigue cuadrando: nadie re-extrae)"
} else {
    $zipTmp = Join-Path $env:TEMP ('cf-payload-' + (Get-Date -Format 'HHmmss') + '.zip')
    [System.IO.Compression.ZipFile]::CreateFromDirectory($Source, $zipTmp, [System.IO.Compression.CompressionLevel]::Optimal, $false)
    $zipBytes = [IO.File]::ReadAllBytes($zipTmp)
    Remove-Item $zipTmp -Force
    "payload (zip)   : {0:N1} MB en {1:N1} s" -f ($zipBytes.Length/1MB), ((Get-Date) - $t0).TotalSeconds
    "  entradas      : {0:N0} ficheros comprimidos" -f (Get-ChildItem $Source -Recurse -File).Count
}

# --- 3. pegar payload + trailer ------------------------------------------------
$hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($zipBytes)
$hash16 = New-Object byte[] 16
[Array]::Copy($hash, 0, $hash16, 0, 16)

if ($reuseHash) {
    $same = $true
    for ($i = 0; $i -lt 16; $i++) { if ($hash16[$i] -ne $reuseHash[$i]) { $same = $false } }
    if (-not $same) { throw "el payload extraido de $PayloadFrom no cuadra con el sha256 de su propio trailer" }
    "integridad      : OK (el payload extraido reproduce su sha256)"
}

$lenBytes = [BitConverter]::GetBytes([int64]$zipBytes.Length)
$outBytes = New-Object byte[] ($stubBytes.Length + $zipBytes.Length + $TRAILER)
[Buffer]::BlockCopy($stubBytes, 0, $outBytes, 0, $stubBytes.Length)
[Buffer]::BlockCopy($zipBytes, 0, $outBytes, $stubBytes.Length, $zipBytes.Length)
[Buffer]::BlockCopy($lenBytes, 0, $outBytes, $stubBytes.Length + $zipBytes.Length, 8)
[Buffer]::BlockCopy($hash16, 0, $outBytes, $stubBytes.Length + $zipBytes.Length + 8, 16)
[Buffer]::BlockCopy($MARKER, 0, $outBytes, $stubBytes.Length + $zipBytes.Length + 24, 16)

$outDir = Split-Path $Out -Parent
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
[IO.File]::WriteAllBytes($Out, $outBytes)

# --- 4. verificacion ----------------------------------------------------------
$read = [IO.File]::ReadAllBytes($Out)
$tail = New-Object byte[] $TRAILER
[Array]::Copy($read, $read.Length - $TRAILER, $tail, 0, $TRAILER)
$markerOk = $true
for ($i = 0; $i -lt 16; $i++) { if ($tail[24 + $i] -ne $MARKER[$i]) { $markerOk = $false } }
$lenBack = [BitConverter]::ToInt64($tail, 0)
$hashBack = ($tail[8..23] | ForEach-Object { $_.ToString('x2') }) -join ''

Add-Type -AssemblyName System.Drawing
$iconOk = $false
$iconInfo = 'sin icono'
try {
    $ic = [System.Drawing.Icon]::ExtractAssociatedIcon($Out)
    $icOk = $false
    if ($ic) {
        $bmp = $ic.ToBitmap()
        $ref = New-Object System.Drawing.Icon((Join-Path $root 'CoreFrame.ico'), 32, 32)
        $refBmp = $ref.ToBitmap()
        $iconOk = $true
        $iconInfo = "$($bmp.Width)x$($bmp.Height)"
        for ($y = 0; $y -lt 32 -and $iconOk; $y++) {
            for ($x = 0; $x -lt 32; $x++) {
                if ($bmp.GetPixel($x, $y).ToArgb() -ne $refBmp.GetPixel($x, $y).ToArgb()) { $iconOk = $false; break }
            }
        }
    }
} catch { $iconInfo = $_.Exception.Message }

""
"=== resultado ==="
"salida          : $Out"
"tamano          : {0:N1} MB ({1:N0} bytes)" -f ($read.Length/1MB), $read.Length
"firma valida    : $markerOk"
"longitud leida  : $lenBack (coincide: $($lenBack -eq $zipBytes.Length))"
"sha256(16)      : $hashBack"
"stamp esperado  : `"$hashBack $lenBack`""
"icono embebido  : $iconOk ($iconInfo)  [comparado pixel a pixel con CoreFrame.ico 32x32]"
""
"Para probar sin tocar la instalacion viva:"
"  & `"$Out`" --install-dir `"$env:TEMP\cftest`" --no-launch"
