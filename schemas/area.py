from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from schemas.proposta import PropostaSchema


class AreaEntradaSchema(BaseModel):
    """Bairro do Rio de Janeiro a ser analisado."""

    # Só letras (com acento), espaços, hífen e apóstrofo: o nome entra na consulta
    # da Overpass, então nada de aspas ou símbolos que alterem a consulta
    bairro: str = Field(
        min_length=2,
        max_length=60,
        pattern=r"^[A-Za-zÀ-ÿ' -]+$",
        examples=["Botafogo"],
    )


class AreaSchema(BaseModel):
    """Resumo de uma análise de bairro já gravada."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bairro: str
    criada_em: datetime
    fonte_dados: str = Field(description='"overpass" ou "arquivo_local" (fallback)')
    total_vias: int
    total_ilhas: int
    metros_malha_principal: float | None


class AreaComPropostasSchema(AreaSchema):
    """Análise de bairro com as propostas de ligação, da maior razão para a menor."""

    propostas: list[PropostaSchema]


class MensagemSchema(BaseModel):
    """Confirmação de uma remoção."""

    mensagem: str
    id: int
