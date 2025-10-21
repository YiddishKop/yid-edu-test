param(
  [string]$DbUser = "yiddi",
  [string]$DbPassword = "",
  [string]$DbName = "exam_db",
  [string]$DbHost = "localhost",
  [string]$DbPort = "5432"
)

Write-Host "[1/5] Creating venv (.venv) if missing..." -ForegroundColor Cyan
python -m venv .venv 2>$null | Out-Null

$pip = Join-Path ".venv" "Scripts\pip.exe"
if (!(Test-Path $pip)) { throw "pip not found in .venv; ensure Python is installed." }

Write-Host "[2/5] Installing Python requirements..." -ForegroundColor Cyan
& $pip install --upgrade pip | Write-Output
if (Test-Path "requirements.txt") {
  & $pip install -r requirements.txt | Write-Output
} else {
  Write-Warning "requirements.txt not found; installing common deps"
  & $pip install streamlit sqlalchemy psycopg2-binary pypandoc python-docx pdfplumber pymupdf Wand tqdm pandas Pillow | Write-Output
}

Write-Host "[3/5] Checking system tools (pandoc, xelatex, magick)..." -ForegroundColor Cyan
function Test-Tool($name){ $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }
if (!(Test-Tool "pandoc")) { Write-Warning "Pandoc not found in PATH (Markdown/LaTeX conversion)." }
if (!(Test-Tool "xelatex")) { Write-Warning "xelatex not found in PATH (LaTeX PDF build)." }
if (!(Test-Tool "magick")) { Write-Warning "ImageMagick 'magick' not found (Wand image conversions)." }

Write-Host "[4/5] Initializing PostgreSQL schema..." -ForegroundColor Cyan
if (!(Test-Path "database/schema.sql")) {
  Write-Warning "database/schema.sql not found; skipping schema initialization."
} else {
  if ([string]::IsNullOrWhiteSpace($DbPassword)) {
    $DbPassword = Read-Host -AsSecureString "Enter PostgreSQL password for user '$DbUser'" | `
      ForEach-Object { (New-Object System.Net.NetworkCredential "", $_).Password }
  }
  $env:PGPASSWORD = $DbPassword
  if (Get-Command psql -ErrorAction SilentlyContinue) {
    & psql -h $DbHost -U $DbUser -d $DbName -p $DbPort -f "database/schema.sql"
    if ($LASTEXITCODE -ne 0) { Write-Warning "psql returned non-zero exit; verify connection and schema." }
  } else {
    Write-Warning "psql not found; install PostgreSQL client tools to apply schema."
  }
}

Write-Host "[5/5] Done. You can run Streamlit apps now:" -ForegroundColor Green
Write-Host "  streamlit run streamlit_view/streamlit_run.py" -ForegroundColor Gray
Write-Host "  streamlit run streamlit_view/streamlit_view_db.py" -ForegroundColor Gray
