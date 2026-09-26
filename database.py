import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# O arquivo SQLite fica em db/ (fora do git). No Docker, essa pasta vira um volume.
PASTA_DB = Path(__file__).resolve().parent / "db"
DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{PASTA_DB / 'conecta_ciclovias.sqlite3'}"
)


def criar_engine(url, **opcoes):
    """Cria a engine do SQLAlchemy com as configurações de que o SQLite precisa."""
    # o FastAPI atende requisições em threads diferentes; o SQLite, por padrão, recusa isso
    engine = create_engine(url, connect_args={"check_same_thread": False}, **opcoes)

    # o SQLite só respeita chaves estrangeiras (e o ON DELETE CASCADE) se isso for ligado
    @event.listens_for(engine, "connect")
    def ligar_chaves_estrangeiras(conexao, _registro):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


PASTA_DB.mkdir(exist_ok=True)
engine = criar_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """Dependência do FastAPI: abre uma sessão por requisição e SEMPRE a fecha.

    O `yield` entrega a sessão para a rota. Quando a rota termina (com sucesso ou
    com erro), a execução volta para cá e o `finally` fecha a sessão.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
