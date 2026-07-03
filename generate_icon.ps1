Add-Type -AssemblyName System.Drawing

$iconPath = "E:\Programming\CoreFrame\CoreFrame.ico"

function New-FrameBitmap {
    param([int]$Size)
    $bmp = New-Object System.Drawing.Bitmap($Size, $Size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.InterpolationMode = 'HighQualityBicubic'
    $g.Clear([System.Drawing.Color]::FromArgb(0, 0, 0, 0))

    $centerX = $Size / 2
    $centerY = $Size / 2
    $cyan = [System.Drawing.Color]::FromArgb(0, 212, 255)
    $lineW = [Math]::Max(1, [int]($Size / 16))
    $pen1 = New-Object System.Drawing.Pen($cyan, $lineW)
    $pen2 = New-Object System.Drawing.Pen($cyan, [Math]::Max(1, [int]($Size / 20)))

    $r1 = $Size * 1.2 / 2
    $pts1 = @()
    for ($i = 0; $i -lt 6; $i++) {
        $angle = $i * [Math]::PI / 3 - [Math]::PI / 2
        $pts1 += New-Object System.Drawing.PointF(($centerX + $r1 * [Math]::Cos($angle)), ($centerY + $r1 * [Math]::Sin($angle)))
    }
    $g.DrawPolygon($pen1, $pts1)

    $r2 = $Size * 0.7 / 2
    $pts2 = @()
    for ($i = 0; $i -lt 6; $i++) {
        $angle = $i * [Math]::PI / 3 - [Math]::PI / 2
        $pts2 += New-Object System.Drawing.PointF(($centerX + $r2 * [Math]::Cos($angle)), ($centerY + $r2 * [Math]::Sin($angle)))
    }
    $g.DrawPolygon($pen2, $pts2)

    $dotR = [Math]::Max(2, [int]($Size / 8))
    $g.FillEllipse([System.Drawing.SolidBrush]::new($cyan), $centerX - $dotR, $centerY - $dotR, $dotR * 2, $dotR * 2)

    $g.Dispose()
    return $bmp
}

# --- Create multi-size .ico manually ---
$sizes = @(16, 32, 48)
$bitmaps = $sizes | ForEach-Object { New-FrameBitmap $_ }

$fs = [System.IO.File]::Open($iconPath, [System.IO.FileMode]::Create)
$bw = New-Object System.IO.BinaryWriter($fs)

$bw.Write([byte]0); $bw.Write([byte]0)           # reserved
$bw.Write([byte]1); $bw.Write([byte]0)           # ICO type (little-endian short 1)
$bw.Write([byte]$bitmaps.Length); $bw.Write([byte]0)  # count (little-endian short)

$offset = 6 + $bitmaps.Length * 16
$imageData = @()

foreach ($bmp in $bitmaps) {
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $data = $ms.ToArray()
    $ms.Dispose()
    
    $w = if ($bmp.Width -ge 256) { 0 } else { $bmp.Width }
    $h = if ($bmp.Height -ge 256) { 0 } else { $bmp.Height }
    
    $bw.Write([byte]$w)
    $bw.Write([byte]$h)
    $bw.Write([byte]0)  # colors
    $bw.Write([byte]0)  # reserved
    $bw.Write([byte]1); $bw.Write([byte]0)  # planes (LE short)
    $bw.Write([byte]32); $bw.Write([byte]0) # bpp (LE short)
    $bw.Write([int]$data.Length)
    $bw.Write([int]$offset)
    
    $imageData += $data
    $offset += $data.Length
}

foreach ($data in $imageData) {
    $bw.Write($data)
}

$bw.Dispose()
$fs.Dispose()
foreach ($bmp in $bitmaps) { $bmp.Dispose() }

Write-Host "Multi-res icon generated: $iconPath"
