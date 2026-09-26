import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import criar_engine
from models import Base


@pytest.fixture
def sessao_factory():
    """Banco SQLite em memória, novo e vazio para cada teste.

    O StaticPool faz todas as sessões usarem a MESMA conexão: sem isso, cada
    conexão nova abriria um banco em memória diferente (e vazio).
    """
    engine = criar_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.fixture
def sessao(sessao_factory):
    db = sessao_factory()
    yield db
    db.close()
