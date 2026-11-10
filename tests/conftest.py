import os

# Precisa vir antes de importar o app: hash de senha rápido e chave fixa nos testes.
os.environ.setdefault("ATALA_PBKDF2_ITERACOES", "1000")
os.environ.setdefault("ATALA_JWT_SECRET", "chave-so-para-testes")
# Histórico sintético desligado por padrão; os testes de test_simulacao.py ligam.
os.environ.setdefault("ATALA_HISTORICO_SIMULADO", "0")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    # Banco em memória, novo a cada teste.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, expire_on_commit=False)

    def db_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = db_teste
    yield TestClient(app)
    app.dependency_overrides.clear()


def cadastrar(client, email="ana@example.com", senha="senha-forte-123", nome="Ana") -> dict:
    """Cria uma conta e devolve os cabeçalhos com o token."""
    r = client.post("/auth/cadastro", json={"nome": nome, "email": email, "senha": senha})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    return cadastrar(client)
