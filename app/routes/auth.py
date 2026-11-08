"""Cadastro, login e dados da conta (tela Ajustes)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app.schemas import CadastroEntrada, LoginEntrada, PreferenciasEntrada, TokenSaida, UsuarioSaida
from app.seguranca import HASH_FALSO, criar_token, gerar_hash_senha, usuario_atual, verificar_senha

router = APIRouter(tags=["Conta"])


def _token(usuario: Usuario) -> TokenSaida:
    return TokenSaida(access_token=criar_token(usuario), usuario=UsuarioSaida.model_validate(usuario))


@router.post("/auth/cadastro", response_model=TokenSaida, status_code=201)
def cadastro(dados: CadastroEntrada, db: Session = Depends(get_db)):
    """Cria a conta e já devolve o token (o usuário entra logado)."""
    email = dados.email.lower()
    if db.scalars(select(Usuario.id).where(Usuario.email == email)).first() is not None:
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail")
    usuario = Usuario(nome=dados.nome.strip(), email=email, senha_hash=gerar_hash_senha(dados.senha))
    db.add(usuario)
    db.commit()
    return _token(usuario)


@router.post("/auth/login", response_model=TokenSaida)
def login(dados: LoginEntrada, db: Session = Depends(get_db)):
    usuario = db.scalars(select(Usuario).where(Usuario.email == dados.email.lower())).first()
    senha_ok = verificar_senha(dados.senha, usuario.senha_hash if usuario else HASH_FALSO)
    if usuario is None or not senha_ok:
        # Mesma mensagem nos dois casos, para não revelar quais e-mails têm conta.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha incorretos")
    return _token(usuario)


@router.get("/usuarios/eu", response_model=UsuarioSaida)
def meus_dados(usuario: Usuario = Depends(usuario_atual)):
    return usuario


@router.patch("/usuarios/eu", response_model=UsuarioSaida)
def atualizar_preferencias(
    dados: PreferenciasEntrada,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    for campo, valor in dados.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(usuario, campo, valor)
    db.add(usuario)
    db.commit()
    return usuario
