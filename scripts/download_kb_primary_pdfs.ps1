param(
  [string]$OutputDir = "knowledge_base/metadata/pdfs",
  [int]$TimeoutSec = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$downloads = @(
  @{ file = "hohenberg_kohn_1964.pdf"; url = "https://journals.aps.org/pr/pdf/10.1103/PhysRev.136.B864" },
  @{ file = "kohn_sham_1965.pdf"; url = "https://journals.aps.org/pr/pdf/10.1103/PhysRev.140.A1133" },
  @{ file = "runge_gross_1984.pdf"; url = "https://journals.aps.org/prl/pdf/10.1103/PhysRevLett.52.997" },
  @{ file = "octopus_2012_arxiv1207_0402.pdf"; url = "https://arxiv.org/pdf/1207.0402.pdf" },
  @{ file = "octopus_2015_arxiv1511_05686.pdf"; url = "https://arxiv.org/pdf/1511.05686.pdf" }
)

$results = @()

foreach ($item in $downloads) {
  $target = Join-Path $OutputDir $item.file
  try {
    Invoke-WebRequest -Uri $item.url -OutFile $target -TimeoutSec $TimeoutSec -ErrorAction Stop
    $size = (Get-Item $target).Length
    Write-Host ("OK   {0}  {1} bytes" -f $item.file, $size)
    $results += [pscustomobject]@{
      file  = $item.file
      url   = $item.url
      ok    = $true
      bytes = $size
      note  = "downloaded"
    }
  }
  catch {
    if (Test-Path $target) {
      Remove-Item -Force $target
    }
    Write-Host ("FAIL {0}  {1}" -f $item.file, $_.Exception.Message)
    $results += [pscustomobject]@{
      file  = $item.file
      url   = $item.url
      ok    = $false
      bytes = 0
      note  = $_.Exception.Message
    }
  }
}

$statusFile = "knowledge_base/metadata/pdf_download_status.json"
$results | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $statusFile

Write-Host "status_written=$statusFile"
