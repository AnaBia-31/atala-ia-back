"""Ponto de entrada da API do Atala.ia.

Rodar localmente (com o venv ativado):
    uvicorn app.main:app --reload
Documentação interativa: http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGENS_EXTRAS
from app.database import criar_tabelas
from app.routes import alertas, auth, historico, produtos


@asynccontextmanager
async def lifespan(_app: FastAPI):
    criar_tabelas()
    yield


app = FastAPI(
    title="Atala.ia API",
    description=(
        "Histórico de preços, alertas e análise 'comprar ou esperar' para a extensão e o app "
        "mobile do Atala.ia.\n\nPara testar rotas com login aqui: faça `POST /auth/login`, copie "
        "o `access_token` e cole no botão **Authorize**."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# A extensão faz requisições a partir de chrome-extension://<id>. Apps mobile nativos
# não passam por CORS. Outros sites (ex.: uma versão web) entram por ATALA_CORS_ORIGENS.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|http://(localhost|127\.0\.0\.1)(:\d+)?)$",
    allow_origins=CORS_ORIGENS_EXTRAS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(produtos.router)
app.include_router(historico.router)
app.include_router(alertas.router)


@app.get("/", tags=["Status"])
def status():
    return {"status": "ok", "app": "Atala.ia", "docs": "/docs"}
