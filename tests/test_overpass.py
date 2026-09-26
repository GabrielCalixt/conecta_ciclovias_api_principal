import json

import httpx
import pytest

from services import overpass
from services.overpass import (
    FONTE_ARQUIVO,
    FONTE_OVERPASS,
    OverpassIndisponivel,
    buscar_vias,
    converter_elementos,
    montar_consulta,
    nome_arquivo,
)

# Resposta mínima da Overpass, escrita à mão no mesmo formato do `out geom`
RESPOSTA_MINIMA = {
    "elements": [
        {
            "type": "way",
            "id": 101,
            "nodes": [1, 2],
            "geometry": [
                {"lat": -22.95, "lon": -43.18},
                {"lat": -22.951, "lon": -43.181},
            ],
            "tags": {"highway": "cycleway"},
        },
        {
            "type": "way",
            "id": 201,
            "nodes": [2, 3, 4],
            "geometry": [
                {"lat": -22.951, "lon": -43.181},
                {"lat": -22.952, "lon": -43.182},
                {"lat": -22.953, "lon": -43.183},
            ],
            "tags": {"highway": "residential", "name": "Rua Voluntários da Pátria"},
        },
        {
            "type": "way",
            "id": 202,
            "nodes": [4, 5],
            "geometry": [
                {"lat": -22.953, "lon": -43.183},
                {"lat": -22.954, "lon": -43.184},
            ],
            "tags": {"highway": "secondary", "cycleway:right": "lane"},
        },
        {"type": "node", "id": 99, "lat": -22.95, "lon": -43.18},
    ]
}


def verificar_invariantes(vias):
    """Regras que valem para QUALQUER lista de vias gerada por converter_elementos."""
    for via in vias:
        assert via["tipo"] in {"ciclovia", "rua"}, (
            f"via {via['id']}: tipo {via['tipo']}"
        )
        assert len(via["nos"]) == len(via["coordenadas"]), (
            f"via {via['id']}: {len(via['nos'])} nós e {len(via['coordenadas'])} coordenadas"
        )


# ---------- converter_elementos ----------


def test_converte_ciclovia_e_rua():
    vias = converter_elementos(RESPOSTA_MINIMA)
    por_id = {via["id"]: via for via in vias}

    assert por_id[101] == {
        "id": 101,
        "tipo": "ciclovia",
        "nos": [1, 2],
        "coordenadas": [[-22.95, -43.18], [-22.951, -43.181]],
    }
    assert por_id[201]["tipo"] == "rua"
    assert por_id[201]["nos"] == [2, 3, 4]
    verificar_invariantes(vias)


def test_rua_com_ciclofaixa_vira_ciclovia():
    por_id = {via["id"]: via for via in converter_elementos(RESPOSTA_MINIMA)}

    assert por_id[202]["tipo"] == "ciclovia"


def test_ignora_elementos_que_nao_sao_way():
    ids = [via["id"] for via in converter_elementos(RESPOSTA_MINIMA)]

    assert ids == [101, 201, 202]


def test_ignora_way_sem_geometria():
    resposta = {"elements": [{"type": "way", "id": 1, "nodes": [1, 2], "tags": {}}]}

    assert converter_elementos(resposta) == []


def test_resposta_vazia():
    assert converter_elementos({"elements": []}) == []


# ---------- dados reais (dados/overpass) ----------

ARQUIVOS_REAIS = sorted(overpass.PASTA_DADOS.glob("*.json"))


@pytest.mark.parametrize("arquivo", ARQUIVOS_REAIS, ids=lambda a: a.stem)
def test_dados_reais_respeitam_invariantes(arquivo):
    resposta = json.loads(arquivo.read_text(encoding="utf-8"))

    vias = converter_elementos(resposta)

    # não dá para exigir ciclovia: Cosme Velho, por exemplo, não tem nenhuma no OSM
    assert vias, f"{arquivo.name} não gerou nenhuma via"
    assert any(via["tipo"] == "rua" for via in vias), "nenhuma rua"
    verificar_invariantes(vias)


# ---------- montar_consulta e nome_arquivo ----------


def test_consulta_filtra_bairro_dentro_do_rio():
    consulta = montar_consulta("Botafogo")

    assert '["name"~"^Botafogo$",i]' in consulta
    assert "rel(area.rio)" in consulta
    assert "out geom;" in consulta


@pytest.mark.parametrize(
    ("bairro", "esperado"),
    [
        ("Botafogo", "botafogo"),
        ("Jardim Botânico", "jardim_botanico"),
        ("São Conrado", "sao_conrado"),
        ("  gávea ", "gavea"),
    ],
)
def test_nome_arquivo(bairro, esperado):
    assert nome_arquivo(bairro) == esperado


# ---------- buscar_vias (cliente com fallback) ----------
#
# O monkeypatch do pytest troca, só durante o teste, uma função por outra.
# Aqui ele troca o httpx.post por uma versão falsa, para simular a Overpass
# (no ar ou fora do ar) sem depender da internet.


class RespostaFalsa:
    """Imita o objeto de resposta do httpx, com o mínimo que o código usa."""

    def __init__(self, dados):
        self.dados = dados

    def raise_for_status(self):
        pass

    def json(self):
        return self.dados


@pytest.fixture
def pasta_dados(tmp_path, monkeypatch):
    """Pasta de dados salvos temporária, com um arquivo para Botafogo."""
    (tmp_path / "botafogo.json").write_text(
        json.dumps(RESPOSTA_MINIMA), encoding="utf-8"
    )
    monkeypatch.setattr(overpass, "PASTA_DADOS", tmp_path)
    return tmp_path


def simular_queda(*args, **kwargs):
    raise httpx.ConnectError("sem internet")


def test_buscar_vias_com_overpass_no_ar(monkeypatch, pasta_dados):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: RespostaFalsa(RESPOSTA_MINIMA))

    vias, fonte = buscar_vias("Botafogo")

    assert fonte == FONTE_OVERPASS
    assert len(vias) == 3


def test_buscar_vias_usa_arquivo_quando_overpass_cai(monkeypatch, pasta_dados):
    monkeypatch.setattr(httpx, "post", simular_queda)

    vias, fonte = buscar_vias("Botafogo")

    assert fonte == FONTE_ARQUIVO
    assert len(vias) == 3


def test_buscar_vias_usa_arquivo_quando_overpass_devolve_erro(monkeypatch, pasta_dados):
    # a Overpass responde 200, mas avisa no "remark" que a consulta estourou o tempo
    com_erro = {"elements": [], "remark": "runtime error: Query timed out"}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: RespostaFalsa(com_erro))

    vias, fonte = buscar_vias("Botafogo")

    assert fonte == FONTE_ARQUIVO
    assert len(vias) == 3


def test_buscar_vias_sem_overpass_e_sem_arquivo(monkeypatch, pasta_dados):
    monkeypatch.setattr(httpx, "post", simular_queda)

    with pytest.raises(OverpassIndisponivel):
        buscar_vias("Urca")
