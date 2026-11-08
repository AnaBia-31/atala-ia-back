"""Configurações lidas de variáveis de ambiente.

No servidor (Render, Railway...), defina essas variáveis no painel do serviço.
Localmente, os valores padrão já funcionam.
"""

import logging
import os
import secrets
from pathlib import Path

PASTA_RAIZ = Path(__file__).resolve().parent.parent


def _url_do_banco() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("ATALA_DATABASE_URL")
    if not url:
        return f"sqlite:///{PASTA_RAIZ / 'atala.db'}"
    # Render/Heroku entregam "postgres://"; o SQLAlchemy quer o nome do driver.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


DATABASE_URL = _url_do_banco()

# Chave que assina os tokens de login. EM PRODUÇÃO, defina ATALA_JWT_SECRET com um
# valor longo e aleatório (ex.: python -c "import secrets; print(secrets.token_urlsafe(48))").
# Sem ela, uma chave temporária é gerada e todos os logins caem quando o servidor reinicia.
JWT_SECRET = os.getenv("ATALA_JWT_SECRET") or ""
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    logging.getLogger("atala").warning(
        "ATALA_JWT_SECRET não definida: usando uma chave temporária (logins expiram ao reiniciar)."
    )
JWT_ALGORITMO = "HS256"
JWT_VALIDADE_DIAS = int(os.getenv("ATALA_JWT_VALIDADE_DIAS", "30"))

# Custo do hash de senha (PBKDF2-SHA256). 600 mil é o recomendado pela OWASP.
PBKDF2_ITERACOES = int(os.getenv("ATALA_PBKDF2_ITERACOES", "600000"))

# Origens web extras liberadas no CORS, separadas por vírgula (ex.: o domínio de um app web).
# Extensões do Chrome e localhost já são liberadas. Apps mobile nativos não usam CORS.
CORS_ORIGENS_EXTRAS = [o.strip() for o in os.getenv("ATALA_CORS_ORIGENS", "").split(",") if o.strip()]
