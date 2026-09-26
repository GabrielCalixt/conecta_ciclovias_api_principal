from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Area(Base):
    """Uma análise de bairro: o que a Overpass devolveu e o que a secundária calculou."""

    __tablename__ = "area"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bairro: Mapped[str] = mapped_column(String(100), index=True)
    # SEM parênteses: a função é chamada a cada INSERT, e não uma vez só na importação
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fonte_dados: Mapped[str] = mapped_column(String(20))
    total_vias: Mapped[int] = mapped_column(Integer)
    total_ilhas: Mapped[int] = mapped_column(Integer)
    # None quando o bairro não tem nenhuma ciclovia
    metros_malha_principal: Mapped[float | None] = mapped_column(Float, nullable=True)

    # apagar a área apaga as propostas dela (cascade)
    propostas: Mapped[list["Proposta"]] = relationship(  # noqa: F821
        back_populates="area", cascade="all, delete-orphan", order_by="Proposta.id"
    )
