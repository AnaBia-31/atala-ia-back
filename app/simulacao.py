"""Histórico de preços SINTÉTICO para a apresentação.

Quando um produto é visto pela primeira vez (nenhum preço salvo no banco), a API
gera 30 dias de preços inventados terminando no preço real de agora, para a
análise e o gráfico já terem o que mostrar. Esses pontos ficam marcados com
`simulado=True` no banco, e a análise avisa `historico_simulado: true`.

Ligar/desligar: variável de ambiente ATALA_HISTORICO_SIMULADO (1 = ligado, 0 = desligado).
Apagar depois da apresentação:  python seed.py --limpar-simulados
"""

import random
import zlib
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import PrecoHistorico, Produto

DIAS_SIMULADOS = 30

# Preço do início do período em relação ao preço final, para cada perfil.
INICIO_POR_PERFIL = {"queda": 1.30, "alta": 0.80, "estavel": 1.0}


def gerar_precos(final: float, perfil: str, rng: random.Random, dias: int) -> list[float]:
    """Caminho de preços com ruído e uma promoção curta no meio, terminando em `final`."""
    base = final * INICIO_POR_PERFIL[perfil]
    precos = []
    for i in range(dias):
        progresso = i / (dias - 1) if dias > 1 else 1
        preco = base + (final - base) * progresso
        ruido = 0.01 if perfil == "estavel" else 0.035
        preco *= 1 + rng.uniform(-ruido, ruido)
        if perfil != "estavel" and dias * 0.4 < i < dias * 0.45:  # promoção relâmpago
            preco *= 0.88
        precos.append(round(preco, 2))
    precos[-1] = round(final, 2)
    return precos


def escolher_perfil(url: str, preco: float, preco_original: float | None) -> str:
    """Perfil coerente com a página e sempre o mesmo para o mesmo produto.

    Se a loja anuncia um desconto grande, o histórico mostra o preço caindo.
    Senão, o perfil é sorteado a partir da URL (para variar entre os produtos).
    """
    if preco_original and preco_original > preco * 1.15:
        return "queda"
    return ("queda", "alta", "estavel")[zlib.crc32(url.encode()) % 3]


def criar_historico_simulado(
    db: Session,
    produto: Produto,
    preco_final: float,
    agora: datetime,
    perfil: str | None = None,
    dias: int = DIAS_SIMULADOS,
) -> None:
    """Grava `dias` pontos diários simulados ANTES de `agora` (o ponto real de agora fica de fora)."""
    perfil = perfil or escolher_perfil(produto.url, preco_final, produto.preco_original)
    rng = random.Random(zlib.crc32(produto.url.encode()))  # mesmo produto -> mesma curva
    # Gera dias+1 preços terminando no preço atual e descarta o último (que é o real).
    precos = gerar_precos(preco_final, perfil, rng, dias + 1)[:-1]
    for i, preco in enumerate(precos):
        coletado = agora - timedelta(days=dias - i, hours=rng.randint(0, 5))
        db.add(PrecoHistorico(produto_id=produto.id, preco=preco, coletado_em=coletado, simulado=True))
