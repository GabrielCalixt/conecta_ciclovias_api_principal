import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app import app
from database import get_db
from services.overpass import OverpassIndisponivel
from services.secundaria import SecundariaIndisponivel

# Vias no formato que a principal manda para a secundária
VIAS_FALSAS = [
    {"id": 101, "tipo": "ciclovia", "nos": [1, 2], "coordenadas": [[-22.95, -43.18], [-22.951, -43.181]]},
    {"id": 201, "tipo": "rua", "nos": [2, 10], "coordenadas": [[-22.951, -43.181], [-22.955, -43.185]]},
]  # fmt: skip

# Resposta do POST /analises da secundária, no formato do contrato.
# Propostas já ordenadas pela razão; a de maior razão NÃO é a de menor metros_construir.
ANALISE_FALSA = {
    "total_ilhas": 3,
    "malha_principal": {"nos": [1, 2, 3, 5], "metros": 452.82},
    "propostas": [
        {"ilha_nos": [10, 11], "metros_ilha": 800.0, "metros_construir": 120.0,
         "caminho": [5, 4, 10], "razao": 6.67},
        {"ilha_nos": [20, 21], "metros_ilha": 15.0, "metros_construir": 30.0,
         "caminho": [1, 30, 20], "razao": 0.5},
    ],
}  # fmt: skip


@pytest.fixture
def cliente(sessao_factory, monkeypatch):
    """TestClient com banco em memória e com a Overpass e a secundária simuladas."""

    def get_db_de_teste():
        db = sessao_factory()
        try:
            yield db
        finally:
            db.close()

    # troca a dependência do banco real pelo banco em memória
    app.dependency_overrides[get_db] = get_db_de_teste
    # troca as chamadas de rede por respostas prontas (os testes não dependem de internet)
    monkeypatch.setattr("app.buscar_vias", lambda bairro: (VIAS_FALSAS, "overpass"))
    monkeypatch.setattr("app.solicitar_analise", lambda vias: ANALISE_FALSA)

    yield TestClient(app)

    app.dependency_overrides.clear()


def criar_area(cliente, bairro="Botafogo"):
    resposta = cliente.post("/areas", json={"bairro": bairro})
    assert resposta.status_code == status.HTTP_201_CREATED, resposta.text
    return resposta.json()


# ---------- POST /areas ----------


def test_post_area_grava_e_devolve_propostas(cliente):
    area = criar_area(cliente)

    assert area["id"] > 0
    assert area["bairro"] == "Botafogo"
    assert area["fonte_dados"] == "overpass"
    assert area["total_vias"] == len(VIAS_FALSAS)
    assert area["total_ilhas"] == 3
    assert area["metros_malha_principal"] == 452.82
    assert [p["razao"] for p in area["propostas"]] == [6.67, 0.5]
    assert {p["status"] for p in area["propostas"]} == {"proposta"}
    assert area["propostas"][0]["caminho"] == [5, 4, 10]


def test_post_area_sem_ciclovias(cliente, monkeypatch):
    sem_ciclovias = {"total_ilhas": 0, "malha_principal": None, "propostas": []}
    monkeypatch.setattr("app.solicitar_analise", lambda vias: sem_ciclovias)

    area = criar_area(cliente)

    assert area["metros_malha_principal"] is None
    assert area["propostas"] == []


def test_post_area_bairro_sem_vias_404(cliente, monkeypatch):
    monkeypatch.setattr("app.buscar_vias", lambda bairro: ([], "overpass"))

    resposta = cliente.post("/areas", json={"bairro": "Bairro Inexistente"})

    assert resposta.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize("bairro", ["", "B", 'Botafogo"];out;', "Rua 123"])
def test_post_area_bairro_invalido_422(cliente, bairro):
    resposta = cliente.post("/areas", json={"bairro": bairro})

    assert resposta.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_post_area_secundaria_fora_do_ar_503(cliente, monkeypatch):
    def secundaria_fora(vias):
        raise SecundariaIndisponivel("conexão recusada")

    monkeypatch.setattr("app.solicitar_analise", secundaria_fora)

    resposta = cliente.post("/areas", json={"bairro": "Botafogo"})

    assert resposta.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "secundária" in resposta.json()["detail"]
    # nada foi gravado pela metade
    assert cliente.get("/areas").json() == []


def test_post_area_overpass_fora_e_sem_dados_salvos_503(cliente, monkeypatch):
    def overpass_fora(bairro):
        raise OverpassIndisponivel("sem internet e sem arquivo")

    monkeypatch.setattr("app.buscar_vias", overpass_fora)

    resposta = cliente.post("/areas", json={"bairro": "Botafogo"})

    assert resposta.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ---------- GET /areas ----------


def test_get_areas_lista_mais_recente_primeiro(cliente):
    criar_area(cliente, "Botafogo")
    criar_area(cliente, "Urca")

    resposta = cliente.get("/areas")

    assert resposta.status_code == status.HTTP_200_OK
    assert [a["bairro"] for a in resposta.json()] == ["Urca", "Botafogo"]
    assert "propostas" not in resposta.json()[0], "a listagem traz só o resumo"


def test_get_areas_filtra_por_bairro(cliente):
    criar_area(cliente, "Botafogo")
    criar_area(cliente, "Urca")

    resposta = cliente.get("/areas", params={"bairro": "bota"})

    assert [a["bairro"] for a in resposta.json()] == ["Botafogo"]


# ---------- GET /areas/{id}/propostas ----------


def test_get_propostas_ordena_por_razao_por_padrao(cliente):
    area = criar_area(cliente)

    resposta = cliente.get(f"/areas/{area['id']}/propostas")

    assert resposta.status_code == status.HTTP_200_OK
    assert [p["razao"] for p in resposta.json()] == [6.67, 0.5]


def test_get_propostas_ordena_por_metros_construir(cliente):
    area = criar_area(cliente)

    resposta = cliente.get(
        f"/areas/{area['id']}/propostas", params={"ordenar_por": "metros_construir"}
    )

    # menos metros a construir primeiro
    assert [p["metros_construir"] for p in resposta.json()] == [30.0, 120.0]


def test_get_propostas_filtra_por_status(cliente):
    area = criar_area(cliente)
    primeira = area["propostas"][0]["id"]
    cliente.put(f"/propostas/{primeira}", json={"status": "aprovada"})

    resposta = cliente.get(
        f"/areas/{area['id']}/propostas", params={"status": "aprovada"}
    )

    assert [p["id"] for p in resposta.json()] == [primeira]


def test_get_propostas_area_inexistente_404(cliente):
    resposta = cliente.get("/areas/999/propostas")

    assert resposta.status_code == status.HTTP_404_NOT_FOUND


def test_get_propostas_ordenacao_invalida_422(cliente):
    area = criar_area(cliente)

    resposta = cliente.get(
        f"/areas/{area['id']}/propostas", params={"ordenar_por": "id"}
    )

    assert resposta.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# ---------- PUT /propostas/{id} ----------


def test_put_proposta_muda_status(cliente):
    area = criar_area(cliente)
    proposta_id = area["propostas"][0]["id"]

    resposta = cliente.put(f"/propostas/{proposta_id}", json={"status": "aprovada"})

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.json()["status"] == "aprovada"
    assert resposta.json()["id"] == proposta_id


def test_put_proposta_inexistente_404(cliente):
    resposta = cliente.put("/propostas/999", json={"status": "aprovada"})

    assert resposta.status_code == status.HTTP_404_NOT_FOUND


def test_put_proposta_status_invalido_422(cliente):
    area = criar_area(cliente)
    proposta_id = area["propostas"][0]["id"]

    resposta = cliente.put(f"/propostas/{proposta_id}", json={"status": "construida"})

    assert resposta.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# ---------- DELETE /areas/{id} ----------


def test_delete_area_remove_area_e_propostas(cliente):
    area = criar_area(cliente)
    proposta_id = area["propostas"][0]["id"]

    resposta = cliente.delete(f"/areas/{area['id']}")

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.json()["id"] == area["id"]
    assert cliente.get("/areas").json() == []
    # a proposta foi junto (cascade)
    put = cliente.put(f"/propostas/{proposta_id}", json={"status": "aprovada"})
    assert put.status_code == status.HTTP_404_NOT_FOUND


def test_delete_area_inexistente_404(cliente):
    resposta = cliente.delete("/areas/999")

    assert resposta.status_code == status.HTTP_404_NOT_FOUND
