"""Tela "Histórico": produtos que o usuário analisou."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import servicos
from app.database import get_db
from app.models import Usuario, Visualizacao, agora
from app.schemas import ItemHistorico, ProdutoSaida, ResumoHistorico
from app.seguranca import usuario_atual

router = APIRouter(prefix="/historico", tags=["Histórico"])


@router.get("", response_model=ResumoHistorico)
def meu_historico(
    dias: int = Query(7, ge=1, le=365, description="7 = 'analisados esta semana'"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    # Última visualização de cada produto no período.
    ultimas = db.execute(
        select(Visualizacao.produto_id, func.max(Visualizacao.visto_em).label("visto_em"))
        .where(
            Visualizacao.usuario_id == usuario.id,
            Visualizacao.visto_em >= agora() - timedelta(days=dias),
        )
        .group_by(Visualizacao.produto_id)
        .order_by(func.max(Visualizacao.visto_em).desc())
    ).all()

    itens: list[ItemHistorico] = []
    economia = 0.0
    for produto_id, visto_em in ultimas:
        produto = servicos.buscar_produto(db, produto_id)
        atual = servicos.preco_atual(db, produto) or 0.0
        pontos = servicos.historico(db, produto, dias=30)
        if pontos and pontos[0].preco > atual:
            economia += pontos[0].preco - atual
        itens.append(
            ItemHistorico(
                produto=ProdutoSaida.model_validate(produto),
                preco_atual=atual,
                variacao_30d_pct=servicos.variacao_30d(db, produto, atual),
                visto_em=visto_em,
            )
        )

    return ResumoHistorico(
        produtos_analisados=len(itens), economia_identificada=round(economia, 2), itens=itens
    )
