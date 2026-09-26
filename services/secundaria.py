import os

import httpx

# No Docker Compose vira http://secundaria:8000 (o nome do serviço no compose)
SECUNDARIA_URL = os.getenv("SECUNDARIA_URL", "http://localhost:8000")
SECUNDARIA_TIMEOUT = float(os.getenv("SECUNDARIA_TIMEOUT", "60"))


class SecundariaIndisponivel(Exception):
    """A API secundária não respondeu ou respondeu com erro."""


def solicitar_analise(vias):
    """Envia as vias para o POST /analises da secundária e devolve o JSON da análise.

    Formato devolvido: {total_ilhas, malha_principal: {nos, metros} | None,
    propostas: [{ilha_nos, metros_ilha, metros_construir, caminho, razao}]},
    com as propostas já ordenadas pela razão, da maior para a menor.
    """
    try:
        resposta = httpx.post(
            f"{SECUNDARIA_URL}/analises",
            json={"vias": vias},
            timeout=SECUNDARIA_TIMEOUT,
        )
        resposta.raise_for_status()
    except httpx.HTTPError as erro:
        raise SecundariaIndisponivel(
            f"A API secundária ({SECUNDARIA_URL}) não respondeu: {erro}"
        ) from erro
    return resposta.json()
