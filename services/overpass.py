import json
import os
import unicodedata
from pathlib import Path

import httpx

from logger import logger

# Instância pública e gratuita da Overpass API (OpenStreetMap). Não exige cadastro nem chave.
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
# Uso justo: a política da Overpass pede um User-Agent que identifique a aplicação
USER_AGENT = "conecta-ciclovias/1.0 (MVP academico PUC-Rio; github.com/GabrielCalixt)"
# Tempo máximo de espera pela Overpass antes de usar os dados salvos
OVERPASS_TIMEOUT = float(os.getenv("OVERPASS_TIMEOUT", "30"))

# Respostas reais da Overpass, salvas pelo scripts/baixar_zona_sul.py (fallback)
PASTA_DADOS = Path(__file__).resolve().parent.parent / "dados" / "overpass"

FONTE_OVERPASS = "overpass"
FONTE_ARQUIVO = "arquivo_local"

# Tipos de via que entram no grafo: ciclovias e as ruas por onde uma ligação pode passar
TIPOS_HIGHWAY = (
    "cycleway|primary|secondary|tertiary|residential|unclassified|living_street|service"
)

# Uma rua com ciclofaixa (lane) ou ciclovia segregada ao lado (track) conta como ciclovia
CHAVES_CICLOFAIXA = ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")
VALORES_CICLOFAIXA = {"lane", "track"}


class OverpassIndisponivel(Exception):
    """A Overpass falhou e não existe arquivo salvo para o bairro."""


def montar_consulta(bairro, timeout=120):
    """Consulta Overpass QL: todas as ruas e ciclovias dentro de um bairro do Rio.

    - `rel(area.rio)` garante que é o bairro do Rio (existe Botafogo em Campinas, por exemplo);
    - `admin_level=10` é o nível dos bairros do Rio no OpenStreetMap;
    - o nome é comparado sem diferenciar maiúsculas (`,i`);
    - `out geom` devolve, para cada via, os IDs dos nós e as coordenadas deles.
    """
    return (
        f"[out:json][timeout:{timeout}];\n"
        'area["name"="Rio de Janeiro"]["admin_level"="8"]->.rio;\n'
        'rel(area.rio)["boundary"="administrative"]["admin_level"="10"]'
        f'["name"~"^{bairro}$",i];\n'
        "map_to_area->.bairro;\n"
        f'way["highway"~"^({TIPOS_HIGHWAY})$"](area.bairro);\n'
        "out geom;"
    )


def nome_arquivo(bairro):
    """Nome do arquivo salvo de um bairro, em snake_case e sem acentos.

    "Jardim Botânico" -> "jardim_botanico", "São Conrado" -> "sao_conrado".
    """
    sem_acento = unicodedata.normalize("NFKD", bairro)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    palavras = "".join(c if c.isalnum() else " " for c in sem_acento.lower()).split()
    return "_".join(palavras)


def classificar_via(tags):
    """Devolve "ciclovia" ou "rua" a partir das tags do OpenStreetMap."""
    if tags.get("highway") == "cycleway":
        return "ciclovia"
    if any(tags.get(chave) in VALORES_CICLOFAIXA for chave in CHAVES_CICLOFAIXA):
        return "ciclovia"
    return "rua"


def converter_elementos(resposta_overpass):
    """Traduz o JSON da Overpass para o formato de vias da API secundária.

    Mantém só os elementos `way` que tenham `nodes` e `geometry`. Em cada via,
    `nos[i]` fica na posição `coordenadas[i]` (listas paralelas).
    """
    vias = []
    for elemento in resposta_overpass.get("elements", []):
        if elemento.get("type") != "way":
            continue

        nos = elemento.get("nodes")
        geometria = elemento.get("geometry")
        if not nos or not geometria or len(nos) != len(geometria):
            continue

        vias.append(
            {
                "id": elemento["id"],
                "tipo": classificar_via(elemento.get("tags", {})),
                "nos": nos,
                "coordenadas": [[ponto["lat"], ponto["lon"]] for ponto in geometria],
            }
        )
    return vias


def consultar_overpass(bairro):
    """Chama a Overpass e devolve o JSON da resposta. Lança exceção se falhar."""
    resposta = httpx.post(
        OVERPASS_URL,
        data={"data": montar_consulta(bairro)},
        headers={"User-Agent": USER_AGENT},
        timeout=OVERPASS_TIMEOUT,
    )
    resposta.raise_for_status()
    dados = resposta.json()  # se vier HTML de erro, lança ValueError

    # a Overpass pode responder 200 com um erro de execução no campo "remark"
    aviso = dados.get("remark", "")
    if "error" in aviso.lower():
        raise ValueError(f"Overpass devolveu erro: {aviso}")
    return dados


def ler_arquivo_salvo(bairro):
    """Lê a resposta salva da Overpass para o bairro, ou None se não existir."""
    arquivo = PASTA_DADOS / f"{nome_arquivo(bairro)}.json"
    if not arquivo.exists():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))


def buscar_vias(bairro):
    """Busca as vias do bairro na Overpass, com fallback para os dados salvos.

    Devolve uma tupla (vias, fonte), em que fonte é "overpass" ou "arquivo_local".
    Lança OverpassIndisponivel se a Overpass falhar e não houver arquivo salvo.
    """
    try:
        dados = consultar_overpass(bairro)
        return converter_elementos(dados), FONTE_OVERPASS
    except (httpx.HTTPError, ValueError) as erro:
        logger.warning("Overpass indisponível (%s), usando dados salvos", erro)

    dados = ler_arquivo_salvo(bairro)
    if dados is None:
        raise OverpassIndisponivel(
            f"A Overpass está indisponível e não há dados salvos para '{bairro}'"
        )
    return converter_elementos(dados), FONTE_ARQUIVO
