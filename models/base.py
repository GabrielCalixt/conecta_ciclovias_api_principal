from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe base de todas as tabelas. O `Base.metadata` conhece todas elas."""
