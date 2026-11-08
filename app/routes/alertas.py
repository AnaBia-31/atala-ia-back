"""Tela "Alertas": avisar quando o preço chegar ao valor desejado."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos
from app.database import get_db
from app.models import Alerta, Usuario
from app.schemas import AlertaAtualizacao, AlertaEntrada, AlertaSaida, ProdutoSaida
from app.seguranca import usuario_atual

router = APIRouter(prefix="/alertas", tags=["Alertas"])


def _saida(db: Session, alerta: Alerta) -> AlertaSaida:
    atual = servicos.preco_atual(db, alerta.produto)
    return AlertaSaida(
        id=alerta.id,
        produto=ProdutoSaida.model_validate(alerta.produto),
        preco_alvo=alerta.preco_alvo,
        preco_atual=atual,
        ativo=alerta.ativo,
        atingido=atual is not None and atual <= alerta.preco_alvo,
        criado_em=alerta.criado_em,
        disparado_em=alerta.disparado_em,
    )


def _buscar(db: Session, alerta_id: int, usuario: Usuario) -> Alerta:
    alerta = db.get(Alerta, alerta_id)
    if alerta is None or alerta.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return alerta


@router.get("", response_model=list[AlertaSaida])
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    alertas = db.scalars(
        select(Alerta).where(Alerta.usuario_id == usuario.id).order_by(Alerta.criado_em.desc())
    )
    return [_saida(db, a) for a in alertas]


@router.post("", response_model=AlertaSaida, status_code=201)
def criar(
    dados: AlertaEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    produto = servicos.buscar_produto(db, dados.produto_id)
    # Um alerta por produto por usuário: se já existe, só atualiza o alvo.
    alerta = db.scalars(
        select(Alerta).where(Alerta.produto_id == produto.id, Alerta.usuario_id == usuario.id)
    ).first()
    if alerta is None:
        alerta = Alerta(usuario_id=usuario.id, produto_id=produto.id, preco_alvo=dados.preco_alvo)
        db.add(alerta)
    alerta.preco_alvo = dados.preco_alvo
    alerta.ativo = True
    alerta.disparado_em = None
    db.flush()
    atual = servicos.preco_atual(db, produto)
    if atual is not None:
        servicos.verificar_alertas(db, produto, atual)
    db.commit()
    return _saida(db, alerta)


@router.get("/pendentes", response_model=list[AlertaSaida])
def pendentes(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Para o service worker da extensão e o app mobile: alertas disparados que ainda não viraram notificação.

    Cada alerta é devolvido uma única vez (fica marcado como notificado).
    """
    alertas = list(
        db.scalars(
            select(Alerta).where(
                Alerta.usuario_id == usuario.id,
                Alerta.ativo.is_(True),
                Alerta.disparado_em.is_not(None),
                Alerta.notificado.is_(False),
            )
        )
    )
    saida = [_saida(db, a) for a in alertas]
    for alerta in alertas:
        alerta.notificado = True
    db.commit()
    return saida


@router.patch("/{alerta_id}", response_model=AlertaSaida)
def atualizar(
    alerta_id: int,
    dados: AlertaAtualizacao,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """Usado pelo botão liga/desliga e para mudar o preço-alvo."""
    alerta = _buscar(db, alerta_id, usuario)
    if dados.preco_alvo is not None:
        alerta.preco_alvo = dados.preco_alvo
        alerta.disparado_em = None
    if dados.ativo is not None:
        alerta.ativo = dados.ativo
        if dados.ativo:
            alerta.disparado_em = None
    db.flush()
    atual = servicos.preco_atual(db, alerta.produto)
    if alerta.ativo and atual is not None:
        servicos.verificar_alertas(db, alerta.produto, atual)
    db.commit()
    return _saida(db, alerta)


@router.delete("/{alerta_id}", status_code=204)
def remover(
    alerta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    db.delete(_buscar(db, alerta_id, usuario))
    db.commit()
    return Response(status_code=204)
