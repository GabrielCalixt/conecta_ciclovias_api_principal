from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Proposta(Base):
    """Um trecho de rua que, se virar ciclovia, liga uma ilha à malha principal."""

    __tablename__ = "proposta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area_id: Mapped[int] = mapped_column(
        ForeignKey("area.id", ondelete="CASCADE"), index=True
    )
    metros_ilha: Mapped[float] = mapped_column(Float)
    metros_construir: Mapped[float] = mapped_column(Float)
    razao: Mapped[float] = mapped_column(Float)
    # listas de IDs de nós do OSM, guardadas como texto JSON
    ilha_nos: Mapped[list[int]] = mapped_column(JSON)
    caminho: Mapped[list[int]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="proposta")

    area: Mapped["Area"] = relationship(back_populates="propostas")  # noqa: F821
