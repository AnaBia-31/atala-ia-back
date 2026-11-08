"""Tela "Produto": registrar o preço visto e devolver a análise."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos
from app.database import get_db
from app.models import Alerta, Produto, Usuario, Visualizacao
from app.schemas import ObservacaoEntrada, PontoHistorico, ProdutoDetalhe, ProdutoSaida
from app.seguranca import usuario_opcional

router = APIRouter(prefix="/produtos", tags=["Produtos"])


def _detalhe(db: Session, produto: Produto, usuario: Usuario | None) -> ProdutoDetalhe:
    alerta_ativo = False
    if usuario:
        alerta_ativo = (
            db.scalars(
                select(Alerta.id).where(
                    Alerta.produto_id == produto.id,
                    Alerta.usuario_id == usuario.id,
                    Alerta.ativo.is_(True),
                )
            ).first()
            is not None
        )
    return ProdutoDetalhe(
        produto=ProdutoSaida.model_validate(produto),
        analise=servicos.analisar_produto(db, produto),
        alerta_ativo=alerta_ativo,
    )


@router.post("/observar", response_model=ProdutoDetalhe)
def observar(
    dados: ObservacaoEntrada,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_opcional),
):
    """Chamado pela extensão ao abrir a página de um produto.

    Funciona sem login (a análise aparece mesmo assim). Com login, o produto
    também entra no Histórico do usuário.
    """
    url = servicos.normalizar_url(str(dados.url))
    produto = db.scalars(select(Produto).where(Produto.url == url)).first()
    if produto is None:
        produto = Produto(url=url, loja=dados.loja, titulo=dados.titulo, moeda=dados.moeda.upper())
        db.add(produto)
    produto.titulo = dados.titulo
    produto.loja = dados.loja
    if dados.imagem_url:
        produto.imagem_url = str(dados.imagem_url)
    db.flush()

    servicos.registrar_preco(db, produto, dados.preco)
    if usuario:
        db.add(Visualizacao(usuario_id=usuario.id, produto_id=produto.id))
    db.commit()
    return _detalhe(db, produto, usuario)


@router.get("/{produto_id}", response_model=ProdutoDetalhe)
def detalhe(
    produto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_opcional),
):
    return _detalhe(db, servicos.buscar_produto(db, produto_id), usuario)


@router.get("/{produto_id}/historico", response_model=list[PontoHistorico])
def historico(produto_id: int, dias: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """Pontos para o gráfico "Últimos 30 dias"."""
    return servicos.historico(db, servicos.buscar_produto(db, produto_id), dias=dias)
