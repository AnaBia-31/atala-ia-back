"""Conexão com o banco de dados.

Localmente usa SQLite (arquivo atala.db), que não precisa instalar nada.
No servidor, defina DATABASE_URL com o endereço do PostgreSQL (veja app/config.py).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    # Necessário só para SQLite, que por padrão não aceita uso em várias threads.
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependência do FastAPI: abre uma sessão por requisição e fecha no final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def criar_tabelas():
    from app import models  # noqa: F401  (registra as tabelas no Base)

    Base.metadata.create_all(bind=engine)
    migrar_colunas_novas(engine)


def migrar_colunas_novas(engine):
    """create_all não altera tabelas que já existem: adiciona aqui as colunas criadas depois."""
    from sqlalchemy import inspect, text

    colunas = {c["name"] for c in inspect(engine).get_columns("precos_historico")}
    if "simulado" not in colunas:
        with engine.begin() as conexao:
            conexao.execute(
                text("ALTER TABLE precos_historico ADD COLUMN simulado BOOLEAN NOT NULL DEFAULT FALSE")
            )
