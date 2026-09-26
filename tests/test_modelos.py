from datetime import datetime

from sqlalchemy import select

from models import Area, Proposta


def criar_area_com_duas_propostas(sessao):
    area = Area(
        bairro="Botafogo",
        fonte_dados="overpass",
        total_vias=10,
        total_ilhas=3,
        metros_malha_principal=1500.0,
        propostas=[
            Proposta(
                metros_ilha=800.0,
                metros_construir=120.0,
                razao=6.67,
                ilha_nos=[10, 11],
                caminho=[5, 4, 10],
            ),
            Proposta(
                metros_ilha=200.0,
                metros_construir=400.0,
                razao=0.5,
                ilha_nos=[20, 21],
                caminho=[1, 30, 20],
            ),
        ],
    )
    sessao.add(area)
    sessao.commit()
    return area.id


def test_cria_area_com_propostas_e_le_de_volta(sessao_factory):
    with sessao_factory() as sessao:
        area_id = criar_area_com_duas_propostas(sessao)

    # sessão nova: garante que os dados vêm do banco, e não da memória do Python
    with sessao_factory() as sessao:
        area = sessao.get(Area, area_id)

        assert area.bairro == "Botafogo"
        assert area.criada_em is not None
        assert len(area.propostas) == 2
        # as listas voltam como listas (o JSON é convertido na ida e na volta)
        assert area.propostas[0].ilha_nos == [10, 11]
        assert area.propostas[0].caminho == [5, 4, 10]


def test_apagar_area_apaga_propostas(sessao):
    area_id = criar_area_com_duas_propostas(sessao)

    sessao.delete(sessao.get(Area, area_id))
    sessao.commit()

    assert sessao.get(Area, area_id) is None
    assert sessao.scalars(select(Proposta)).all() == []


def test_status_padrao_da_proposta(sessao):
    criar_area_com_duas_propostas(sessao)

    propostas = sessao.scalars(select(Proposta)).all()

    assert {proposta.status for proposta in propostas} == {"proposta"}


def test_data_de_criacao_e_a_do_insert(sessao):
    # pega o bug do `default=datetime.now()`: com parênteses, todas as áreas
    # teriam a mesma data, a da importação do módulo (anterior ao início do teste)
    # hora local, sem fuso, igual ao que o modelo grava
    inicio_do_teste = datetime.now()  # noqa: DTZ005

    area = sessao.get(Area, criar_area_com_duas_propostas(sessao))

    assert area.criada_em >= inicio_do_teste
