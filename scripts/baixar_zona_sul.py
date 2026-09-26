"""Baixa da Overpass as ruas e ciclovias dos bairros da Zona Sul do Rio.

Cada resposta é salva em dados/overpass/<bairro>.json e serve de fallback
(se a Overpass cair) e de dado real para os testes.

Uso, na raiz do repositório e com o venv ativo:
    python -m scripts.baixar_zona_sul                 # baixa os bairros que faltam
    python -m scripts.baixar_zona_sul Leme Urca       # baixa só estes
    python -m scripts.baixar_zona_sul --forcar        # baixa todos de novo
"""

import json
import sys
import time

import httpx

from services.overpass import (
    OVERPASS_URL,
    PASTA_DADOS,
    USER_AGENT,
    montar_consulta,
    nome_arquivo,
)

BAIRROS_ZONA_SUL = [
    "Leme",
    "Copacabana",
    "Ipanema",
    "Leblon",
    "Lagoa",
    "Jardim Botânico",
    "Gávea",
    "Humaitá",
    "Botafogo",
    "Urca",
    "Flamengo",
    "Laranjeiras",
    "Cosme Velho",
    "Catete",
    "Glória",
    "São Conrado",
    "Vidigal",
    "Rocinha",
]

# Uso justo da API pública: espera entre uma requisição e outra
INTERVALO_SEGUNDOS = 10
# Em 429 (limite de uso) ou 504 (servidor ocupado), espera cada vez mais e tenta de novo
ESPERAS_NOVA_TENTATIVA = (30, 60, 90)
STATUS_TEMPORARIOS = {429, 504}


def baixar(bairro):
    """Baixa um bairro e salva o arquivo. Devolve o número de vias ou lança exceção."""
    resposta = httpx.post(
        OVERPASS_URL,
        data={"data": montar_consulta(bairro)},
        headers={"User-Agent": USER_AGENT},
        timeout=180,
    )
    resposta.raise_for_status()
    dados = resposta.json()

    if "error" in dados.get("remark", "").lower():
        raise ValueError(dados["remark"])
    vias = [e for e in dados.get("elements", []) if e.get("type") == "way"]
    if not vias:
        raise ValueError("resposta sem nenhuma via")

    arquivo = PASTA_DADOS / f"{nome_arquivo(bairro)}.json"
    # JSON compacto (sem indentação) para os arquivos ocuparem menos espaço no repositório
    arquivo.write_text(
        json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return len(vias)


def baixar_com_novas_tentativas(bairro):
    """Chama baixar(); se a Overpass pedir para esperar (429/504), espera e repete."""
    for espera in ESPERAS_NOVA_TENTATIVA:
        try:
            return baixar(bairro)
        except httpx.HTTPStatusError as erro:
            if erro.response.status_code not in STATUS_TEMPORARIOS:
                raise
            codigo = erro.response.status_code
            print(f"{bairro}: Overpass respondeu {codigo}, nova tentativa em {espera}s")
            time.sleep(espera)
    return baixar(bairro)


def main(argumentos):
    forcar = "--forcar" in argumentos
    pedidos = [a for a in argumentos if not a.startswith("--")] or BAIRROS_ZONA_SUL
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)

    falhas = []
    for indice, bairro in enumerate(pedidos):
        arquivo = PASTA_DADOS / f"{nome_arquivo(bairro)}.json"
        if arquivo.exists() and not forcar:
            print(f"{bairro}: já existe, pulando")
            continue

        if indice > 0:
            time.sleep(INTERVALO_SEGUNDOS)
        inicio = time.perf_counter()
        try:
            total = baixar_com_novas_tentativas(bairro)
        except (httpx.HTTPError, ValueError) as erro:
            print(f"{bairro}: FALHOU ({erro})")
            falhas.append(bairro)
            continue
        segundos = time.perf_counter() - inicio
        print(f"{bairro}: {total} vias em {segundos:.1f}s -> {arquivo.name}")

    if falhas:
        print("\nRode de novo só para os que faltaram:")
        print("python -m scripts.baixar_zona_sul " + " ".join(f'"{b}"' for b in falhas))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
