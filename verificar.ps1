# Roda lint, formatação e testes EM SEQUÊNCIA e para no primeiro erro.
# Uso (com o venv ativo, na raiz do repositório):  .\verificar.ps1

$passos = @(
    @{ nome = "ruff check --fix"; cmd = { ruff check . --fix } },
    @{ nome = "ruff format";      cmd = { ruff format . } },
    @{ nome = "ruff check";       cmd = { ruff check . } },
    @{ nome = "pytest";           cmd = { pytest } }
)

foreach ($passo in $passos) {
    Write-Host "`n==> $($passo.nome)" -ForegroundColor Cyan
    & $passo.cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFALHOU em: $($passo.nome). Corrija antes de commitar." -ForegroundColor Red
        exit 1
    }
}

Write-Host "`nTudo verde. Confira o que vai entrar no commit:" -ForegroundColor Green
git status
