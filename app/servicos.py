"""Funções compartilhadas entre as rotas."""

from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analise import analisar
from app.models import Alerta, PrecoHistorico, Produto, agora
from app.schemas import Analise

# Não grava um novo ponto se o preço for igual ao último visto há menos disso.
INTERVALO_MINIMO_ENTRE_PONTOS = timedelta(hours=1)


def normalizar_url(url: str) -> str:
    """Remove parâmetros de rastreamento (?utm=..., #...) para o mesmo produto não virar dois."""
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc.lower(), partes.path.rstrip("/"), "", ""))


def buscar_produto(db: Session, produto_id: int) -> Produto:
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return produto


def historico(db: Session, produto: Produto, dias: int | None = None) -> list[PrecoHistorico]:
    consulta = select(PrecoHistorico).where(PrecoHistorico.produto_id == produto.id)
    if dias is not None:
        consulta = consulta.where(PrecoHistorico.coletado_em >= agora() - timedelta(days=dias))
    return list(db.scalars(consulta.order_by(PrecoHistorico.coletado_em)))


def _ultimo_ponto(db: Session, produto: Produto) -> PrecoHistorico | None:
    return db.scalars(
        select(PrecoHistorico)
        .where(PrecoHistorico.produto_id == produto.id)
        .order_by(PrecoHistorico.coletado_em.desc())
        .limit(1)
    ).first()


def preco_atual(db: Session, produto: Produto) -> float | None:
    ultimo = _ultimo_ponto(db, produto)
    return ultimo.preco if ultimo else None


def analisar_produto(db: Session, produto: Produto) -> Analise:
    pontos = [(p.coletado_em, p.preco) for p in historico(db, produto, dias=60)]
    atual = pontos[-1][1] if pontos else 0.0
    return analisar(pontos, atual, agora=agora(), preco_original=produto.preco_original)


def registrar_preco(db: Session, produto: Produto, preco: float) -> None:
    ultimo = _ultimo_ponto(db, produto)
    repetido = (
        ultimo is not None
        and abs(ultimo.preco - preco) < 0.005
        and agora() - ultimo.coletado_em < INTERVALO_MINIMO_ENTRE_PONTOS
    )
    if not repetido:
        db.add(PrecoHistorico(produto_id=produto.id, preco=preco))
    verificar_alertas(db, produto, preco)


def verificar_alertas(db: Session, produto: Produto, preco: float) -> None:
    """Marca como disparados os alertas ativos cujo preço-alvo foi atingido (de todos os usuários)."""
    alertas = db.scalars(
        select(Alerta).where(
            Alerta.produto_id == produto.id,
            Alerta.ativo.is_(True),
            Alerta.disparado_em.is_(None),
            Alerta.preco_alvo >= preco,
        )
    )
    for alerta in alertas:
        alerta.disparado_em = agora()
        alerta.notificado = False


def variacao_30d(db: Session, produto: Produto, atual: float) -> float | None:
    pontos = historico(db, produto, dias=30)
    if not pontos or pontos[0].preco == 0:
        return None
    return round((atual - pontos[0].preco) / pontos[0].preco * 100, 1)
