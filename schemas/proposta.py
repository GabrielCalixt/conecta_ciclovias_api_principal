from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusProposta = Literal["proposta", "aprovada", "descartada"]


class PropostaSchema(BaseModel):
    """Um trecho de rua que, se virar ciclovia, liga uma ilha à malha principal."""

    # permite montar o schema direto a partir do objeto do SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    area_id: int
    metros_ilha: float = Field(
        description="Metros de ciclovia da ilha que passam a se conectar"
    )
    metros_construir: float = Field(
        description="Metros de rua que precisam virar ciclovia"
    )
    razao: float = Field(
        description="metros_ilha / metros_construir: quanto maior, melhor"
    )
    ilha_nos: list[int] = Field(
        description="IDs dos nós do OpenStreetMap que formam a ilha"
    )
    caminho: list[int] = Field(
        description="IDs dos nós do trecho a construir, da malha até a ilha"
    )
    status: StatusProposta


class AtualizaStatusSchema(BaseModel):
    """Novo status de uma proposta. Qualquer outro valor devolve 422."""

    status: StatusProposta = Field(examples=["aprovada"])
