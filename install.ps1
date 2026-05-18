# Plugin Claude Code: anonymize-data — install Windows (PowerShell)
# Usage: irm https://raw.githubusercontent.com/ecompabgof/anonymize-data/main/install.ps1 | iex
#   OR: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

$PluginName = "anonymize-data"
$PluginDir = "$env:USERPROFILE\.claude\plugins\$PluginName"
$RepoUrl = "https://github.com/ecompabgof/anonymize-data"

Write-Host ""
Write-Host "  Claude Code Plugin: anonymize-data v2.0 (Windows)"
Write-Host "  Anonymisation locale RGPD avant Claude"
Write-Host ""

# 1. Check winget
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  Write-Host "  ❌ winget introuvable. Installe-le via Microsoft Store ('App Installer') puis relance."
  exit 1
}

# 2. Check Python
$pythonExe = $null
foreach ($cmd in @("python", "python3", "py")) {
  if (Get-Command $cmd -ErrorAction SilentlyContinue) {
    $version = & $cmd --version 2>&1
    if ($version -match "Python 3\.(\d+)") {
      $minor = [int]$Matches[1]
      if ($minor -ge 10) {
        $pythonExe = (Get-Command $cmd).Source
        Write-Host "  Python OK: $pythonExe ($version)"
        break
      }
    }
  }
}

if (-not $pythonExe) {
  Write-Host "  Installation Python 3.11 via winget..."
  winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
  Write-Host "  ⚠ Ferme et relance PowerShell, puis relance install.ps1"
  exit 0
}

# 3. Install system tools via winget
Write-Host ""
Write-Host "  Installation outils système..."

$winget_pkgs = @(
  @{id="Git.Git"; name="Git"},
  @{id="UB-Mannheim.TesseractOCR"; name="Tesseract OCR"},
  @{id="ArtifexSoftware.GhostScript"; name="Ghostscript"}
)

foreach ($pkg in $winget_pkgs) {
  Write-Host "  → $($pkg.name)..."
  winget install -e --id $pkg.id --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
}

# 4. Add Tesseract + Ghostscript to PATH for current session
$tesseractPath = "C:\Program Files\Tesseract-OCR"
$gsBin = Get-ChildItem "C:\Program Files\gs\gs*\bin" -ErrorAction SilentlyContinue | Select-Object -First 1
if (Test-Path $tesseractPath) { $env:Path += ";$tesseractPath" }
if ($gsBin) { $env:Path += ";$($gsBin.FullName)" }

# 5. Clone or update plugin
Write-Host ""
Write-Host "  Récupération plugin..."
if (Test-Path $PluginDir) {
  Write-Host "  Déjà présent: $PluginDir (git pull)"
  Push-Location $PluginDir
  & git pull --quiet 2>&1 | Out-Null
  Pop-Location
} else {
  New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\plugins" | Out-Null
  & git clone --quiet $RepoUrl $PluginDir
  Write-Host "  Cloné depuis $RepoUrl"
}

# 6. Create venv
Write-Host ""
Write-Host "  Création venv Python..."
& $pythonExe -m venv "$PluginDir\.venv"
$venvPython = "$PluginDir\.venv\Scripts\python.exe"
$venvPip = "$PluginDir\.venv\Scripts\pip.exe"

# 7. Install Python deps
Write-Host "  Installation dépendances Python (3-5min)..."
& $venvPip install --upgrade pip --quiet
& $venvPip install --quiet -r "$PluginDir\requirements.txt"

# 8. spaCy models (direct URL bypass)
Write-Host ""
Write-Host "  Téléchargement modèles spaCy fr+en..."
& $venvPip install --quiet `
  "https://github.com/explosion/spacy-models/releases/download/fr_core_news_md-3.8.0/fr_core_news_md-3.8.0-py3-none-any.whl" `
  "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

# 9. Create Windows hook wrapper (uses Python instead of bash)
Write-Host ""
Write-Host "  Configuration hook Windows..."
$hookPs = @"
# Windows hook wrapper (PowerShell) — calls Python anonymizer
`$input = [Console]::In.ReadToEnd()
& "$venvPython" "$PluginDir\scripts\hook_runner.py" `$input
"@
$hookPs | Out-File -FilePath "$PluginDir\hooks\pre-prompt.ps1" -Encoding UTF8

# 10. Smoke test
Write-Host ""
Write-Host "  Test rapide..."
$testFile = "$env:TEMP\anonymize_smoke.txt"
"Madame Jean DUPONT, 14 rue de la Paix, 75001 Paris. Tel: 06 12 34 56 78. NIR: 282017864617737" | Out-File $testFile -Encoding UTF8
$result = & $venvPython "$PluginDir\scripts\anonymize.py" $testFile 2>&1
Remove-Item $testFile -ErrorAction SilentlyContinue

if ($result -match "\[CIVILITE\]|\[NOM\]|\[ADRESSE\]") {
  Write-Host "  ✓ Test OK"
  Write-Host ""
  Write-Host "  Résultat anonymisé:"
  Write-Host "  $result"
} else {
  Write-Host "  ⚠ Test inconcluant. Résultat:"
  Write-Host "  $result"
}

Write-Host ""
Write-Host "  ✓ Installation terminée"
Write-Host ""
Write-Host "  Usage dans Claude Code:"
Write-Host "    @fiche_paye.pdf analyse ce salaire"
Write-Host "    @journal.xlsx fais total"
Write-Host "    @photo.jpg lis cette photo"
Write-Host ""
Write-Host "  IMPORTANT:"
Write-Host "  1. Ferme Claude Code complètement"
Write-Host "  2. Relance Claude Code"
Write-Host "  3. Le plugin sera actif"
Write-Host ""
