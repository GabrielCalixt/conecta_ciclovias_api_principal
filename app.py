from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import engine, get_db
from logger import logger
from models import Area, Base, Proposta
from schemas.area import (
    AreaComPropostasSchema,
    AreaEntradaSchema,
    AreaSchema,
    MensagemSchema,
)
from schemas.erro import ErroSchema
from schemas.proposta import AtualizaStatusSchema, PropostaSchema, StatusProposta
from services.overpass import OverpassIndisponivel, buscar_vias
from services.secundaria import SecundariaIndisponivel, solicitar_analise

tags_metadata = [
    {"name": "Saúde", "description": "Verifica se a API está no ar"},
    {
        "name": "Áreas",
        "description": "Análises de bairro: busca as vias no OpenStreetMap (Overpass), "
        "pede a análise à API secundária e grava o resultado",
    },
    {
        "name": "Propostas",
        "description": "Trechos sugeridos para ligar as ilhas de ciclovia à malha principal",
    },
]

app = FastAPI(
    title="Conecta Ciclovias — API principal",
    description="Planejador de expansão de ciclovias no Rio de Janeiro. "
    "Dados de vias © OpenStreetMap contributors (licença ODbL), via Overpass API.",
    openapi_tags=tags_metadata,
)

# cria as tabelas no SQLite, se ainda não existirem
Base.metadata.create_all(bind=engine)

# sessão do banco aberta e fechada a cada requisição (ver database.get_db)
SessaoDB = Annotated[Session, Depends(get_db)]

ERRO_404 = {status.HTTP_404_NOT_FOUND: {"model": ErroSchema}}
ERRO_503 = {status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErroSchema}}


def buscar_ou_404(db, modelo, id_registro, nome):
    """Busca um registro pelo ID ou responde 404."""
    registro = db.get(modelo, id_registro)
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{nome} {id_registro} não encontrada",
        )
    return registro


@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse(url="/docs")


@app.get("/saude", tags=["Saúde"])
def saude():
    return {"status": "ok"}


@app.post(
    "/areas",
    status_code=status.HTTP_201_CREATED,
    response_model=AreaComPropostasSchema,
    tags=["Áreas"],
    responses={**ERRO_404, **ERRO_503},
)
def criar_area(dados: AreaEntradaSchema, db: SessaoDB):
    """Analisa um bairro do Rio e grava as propostas de ligação entre ciclovias.

    1. Busca as ruas e ciclovias do bairro na Overpass API (OpenStreetMap). Se a
       Overpass falhar, usa os dados salvos do bairro (`fonte_dados = arquivo_local`).
    2. Envia as vias para o `POST /analises` da API secundária (BFS + Dijkstra).
    3. Grava a área e as propostas, ranqueadas pela razão metros conectados / metros
       a construir.

    Devolve **404** se o bairro não tiver vias (nome errado ou sem acento) e **503**
    se a Overpass (sem dados salvos) ou a API secundária estiverem fora do ar.
    """
    bairro = dados.bairro.strip()

    try:
        vias, fonte = buscar_vias(bairro)
    except OverpassIndisponivel as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(erro)
        ) from erro

    if not vias:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma via encontrada para o bairro '{bairro}'. "
            "Confira o nome, com acentos (ex.: 'Jardim Botânico').",
        )

    try:
        analise = solicitar_analise(vias)
    except SecundariaIndisponivel as erro:
        logger.error("%s", erro)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A API secundária está fora do ar. Tente novamente em instantes.",
        ) from erro

    malha = analise["malha_principal"]
    area = Area(
        bairro=bairro,
        fonte_dados=fonte,
        total_vias=len(vias),
        total_ilhas=analise["total_ilhas"],
        metros_malha_principal=malha["metros"] if malha else None,
        propostas=[
            Proposta(
                metros_ilha=proposta["metros_ilha"],
                metros_construir=proposta["metros_construir"],
                razao=proposta["razao"],
                ilha_nos=proposta["ilha_nos"],
                caminho=proposta["caminho"],
            )
            for proposta in analise["propostas"]
        ],
    )
    db.add(area)
    db.commit()
    db.refresh(area)

    logger.info(
        "Área %s gravada: %s (%s vias, %s propostas, fonte %s)",
        area.id,
        bairro,
        len(vias),
        len(area.propostas),
        fonte,
    )
    return area


@app.get("/areas", response_model=list[AreaSchema], tags=["Áreas"])
def listar_areas(
    db: SessaoDB,
    bairro: Annotated[
        str | None,
        Query(description="Filtra por parte do nome do bairro (ignora maiúsculas)"),
    ] = None,
):
    """Lista as áreas analisadas, da mais recente para a mais antiga."""
    consulta = select(Area).order_by(Area.criada_em.desc(), Area.id.desc())
    if bairro:
        consulta = consulta.where(Area.bairro.ilike(f"%{bairro}%"))
    return db.scalars(consulta).all()


@app.get(
    "/areas/{area_id}/propostas",
    response_model=list[PropostaSchema],
    tags=["Propostas"],
    responses=ERRO_404,
)
def listar_propostas(
    area_id: int,
    db: SessaoDB,
    status_proposta: Annotated[
        StatusProposta | None,
        Query(alias="status", description="Filtra pelo status da proposta"),
    ] = None,
    ordenar_por: Annotated[
        Literal["razao", "metros_construir"],
        Query(
            description="`razao`: maior primeiro (mais ciclovia por metro construído). "
            "`metros_construir`: menor obra primeiro."
        ),
    ] = "razao",
):
    """Lista as propostas de uma área, com filtro por status e ordenação."""
    buscar_ou_404(db, Area, area_id, "Área")

    consulta = select(Proposta).where(Proposta.area_id == area_id)
    if status_proposta:
        consulta = consulta.where(Proposta.status == status_proposta)
    if ordenar_por == "razao":
        consulta = consulta.order_by(Proposta.razao.desc())
    else:
        consulta = consulta.order_by(Proposta.metros_construir.asc())
    return db.scalars(consulta).all()


@app.put(
    "/propostas/{proposta_id}",
    response_model=PropostaSchema,
    tags=["Propostas"],
    responses=ERRO_404,
)
def atualizar_status(proposta_id: int, dados: AtualizaStatusSchema, db: SessaoDB):
    """Muda o status de uma proposta: `proposta`, `aprovada` ou `descartada`."""
    proposta = buscar_ou_404(db, Proposta, proposta_id, "Proposta")
    proposta.status = dados.status
    db.commit()
    db.refresh(proposta)
    logger.info("Proposta %s agora está %s", proposta_id, dados.status)
    return proposta


@app.delete(
    "/areas/{area_id}",
    response_model=MensagemSchema,
    tags=["Áreas"],
    responses=ERRO_404,
)
def remover_area(area_id: int, db: SessaoDB):
    """Remove a área e, em cascata, todas as propostas dela."""
    area = buscar_ou_404(db, Area, area_id, "Área")
    db.delete(area)
    db.commit()
    logger.info("Área %s removida", area_id)
    return MensagemSchema(mensagem="Área removida, junto com as propostas", id=area_id)
