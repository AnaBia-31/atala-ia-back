"""Senhas e tokens de login.

- Senhas: guardadas só como hash PBKDF2-SHA256 com salt (biblioteca padrão do Python).
- Login: devolve um token JWT. A extensão e o app mobile mandam esse token em toda
  requisição no cabeçalho  Authorization: Bearer <token>.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import Usuario

_ALGORITMO_SENHA = "pbkdf2_sha256"


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()


def gerar_hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    iteracoes = config.PBKDF2_ITERACOES
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, iteracoes)
    return f"{_ALGORITMO_SENHA}${iteracoes}${_b64(salt)}${_b64(digest)}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        algoritmo, iteracoes, salt, esperado = senha_hash.split("$")
        if algoritmo != _ALGORITMO_SENHA:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), base64.b64decode(salt), int(iteracoes))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64(digest), esperado)


# Hash calculado uma vez para gastar o mesmo tempo quando o e-mail não existe
# (assim não dá para descobrir quais e-mails têm conta medindo o tempo da resposta).
HASH_FALSO = gerar_hash_senha(secrets.token_urlsafe(16))


def criar_token(usuario: Usuario) -> str:
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario.id),
        "iat": agora,
        "exp": agora + timedelta(days=config.JWT_VALIDADE_DIAS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITMO)


_bearer = HTTPBearer(auto_error=False)
_NAO_AUTORIZADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Faça login para continuar",
    headers={"WWW-Authenticate": "Bearer"},
)


def _usuario_do_token(credenciais: HTTPAuthorizationCredentials | None, db: Session) -> Usuario | None:
    if credenciais is None:
        return None
    try:
        payload = jwt.decode(credenciais.credentials, config.JWT_SECRET, algorithms=[config.JWT_ALGORITMO])
        usuario_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _NAO_AUTORIZADO
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise _NAO_AUTORIZADO
    return usuario


def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """Dependência para rotas que exigem login."""
    usuario = _usuario_do_token(credenciais, db)
    if usuario is None:
        raise _NAO_AUTORIZADO
    return usuario


def usuario_opcional(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Dependência para rotas que funcionam com ou sem login."""
    return _usuario_do_token(credenciais, db)
