param(
    [Parameter(Mandatory=$true)][string]$BaseUrl,
    [int]$Repeat = 1,
    [int]$MaxRepos = 3,
    [int]$Discover = 0,
    [int]$LlmPerRepo = 1,
    [string]$Output,
    [string]$ServerSsh,
    [string]$GpuSsh,
    [switch]$EnsureServices,
    [switch]$SkipBrowser,
    [switch]$Resume,
    [string]$PublishTo
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = Join-Path $repoRoot 'outputs/validation-runtime'
$python = Join-Path $runtime '.venv/Scripts/python.exe'
if (-not $Output) { $Output = Join-Path $repoRoot ('outputs/validation-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
if (-not (Test-Path $python)) {
    python -m venv (Join-Path $runtime '.venv')
    if ($LASTEXITCODE) { throw 'Python 3.11+ 환경을 준비하지 못했습니다.' }
}
if (-not $SkipBrowser) {
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE) { throw 'Playwright 설치 실패' }
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $runtime 'browsers'
    & $python -m playwright install chromium
    if ($LASTEXITCODE) { throw 'Chromium 설치 실패' }
}
$runArgs = @((Join-Path $PSScriptRoot 'runner.py'), '--base-url', $BaseUrl, '--output', $Output,
    '--repeat', $Repeat, '--max-repos', $MaxRepos, '--discover', $Discover, '--llm-per-repo', $LlmPerRepo,
    '--rescan', '--mcp', '--incident-drafts')
if (-not $SkipBrowser) { $runArgs += '--browser' }
if ($Resume) { $runArgs += '--resume' }
if ($ServerSsh) { $runArgs += @('--server-ssh', $ServerSsh) }
if ($GpuSsh) { $runArgs += @('--gpu-ssh', $GpuSsh) }
if ($EnsureServices) { $runArgs += '--ensure-services' }
& $python @runArgs
$runExit = $LASTEXITCODE
if ($PublishTo) {
    & $python (Join-Path $PSScriptRoot 'publish.py') --ssh $PublishTo --output $Output
    if ($LASTEXITCODE) { throw '검증 결과 공개 실패' }
}
Write-Host ('검증 화면: ' + (Join-Path $Output 'public/index.html'))
exit $runExit
