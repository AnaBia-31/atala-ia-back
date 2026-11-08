"""Popula o banco com DADOS FICTÍCIOS para demonstração.

Cria os produtos que aparecem no protótipo (fone, copo Stanley, tinta, mouse),
cada um com 60 dias de preços inventados, além de uma conta de demonstração
com histórico e alertas. Use para apresentar a extensão sem precisar esperar
semanas coletando preços reais.

    python seed.py          # apaga os dados de demonstração e recria
"""

import random
from datetime import timedelta

from sqlalchemy import delete, select

from app.database import SessionLocal, criar_tabelas
from app.models import Alerta, PrecoHistorico, Produto, Usuario, Visualizacao, agora
from app.seguranca import gerar_hash_senha

# Conta só para a apresentação. Não use essa senha em nenhum outro lugar.
EMAIL_DEMO = "demo@atala.ia"
SENHA_DEMO = "demo1234"

# (titulo, loja, preço base, preço final, preço-alvo do alerta, perfil)
# perfil: "queda" termina perto do mínimo, "alta" termina perto do máximo, "estavel" oscila pouco
PRODUTOS = [
    ("Fone de ouvido bluetooth", "Mercado Livre", 449.90, 319.99, 250.00, "queda"),
    ("Copo Stanley", "Amazon", 189.90, 239.90, 150.00, "alta"),
    ("Tinta Guache Himi", "Shopee", 89.90, 89.90, 60.00, "estavel"),
    ("Mouse Classic Box", "Mercado Livre", 19.90, 15.00, 10.00, "queda"),
]


def gerar_precos(base: float, final: float, perfil: str, dias: int, rng: random.Random) -> list[float]:
    """Caminho de preços com ruído, uma promoção curta no meio e chegada ao preço final."""
    precos = []
    for i in range(dias):
        progresso = i / (dias - 1)
        preco = base + (final - base) * progresso
        ruido = 0.01 if perfil == "estavel" else 0.035
        preco *= 1 + rng.uniform(-ruido, ruido)
        if perfil != "estavel" and dias * 0.4 < i < dias * 0.45:  # promoção relâmpago
            preco *= 0.88
        precos.append(round(preco, 2))
    precos[-1] = final
    return precos


def main() -> None:
    criar_tabelas()
    rng = random.Random(42)  # sempre gera os mesmos dados
    db = SessionLocal()
    try:
        urls = [f"https://demo.atala-ia.local/{i}" for i in range(len(PRODUTOS))]
        antigos = list(db.scalars(select(Produto).where(Produto.url.in_(urls))))
        for p in antigos:
            db.execute(delete(Alerta).where(Alerta.produto_id == p.id))
            db.execute(delete(Visualizacao).where(Visualizacao.produto_id == p.id))
            db.delete(p)
        db.commit()

        usuario = db.scalars(select(Usuario).where(Usuario.email == EMAIL_DEMO)).first()
        if usuario is None:
            usuario = Usuario(nome="Conta Demo", email=EMAIL_DEMO, senha_hash=gerar_hash_senha(SENHA_DEMO))
            db.add(usuario)
            db.flush()

        hoje = agora()
        for i, (titulo, loja, base, final, alvo, perfil) in enumerate(PRODUTOS):
            produto = Produto(url=urls[i], loja=loja, titulo=titulo)
            db.add(produto)
            db.flush()
            dias = 60
            for d, preco in enumerate(gerar_precos(base, final, perfil, dias, rng)):
                coletado = hoje - timedelta(days=dias - 1 - d, hours=rng.randint(0, 5))
                db.add(PrecoHistorico(produto_id=produto.id, preco=preco, coletado_em=coletado))
            db.add(Visualizacao(usuario_id=usuario.id, produto_id=produto.id,
                                visto_em=hoje - timedelta(days=i)))
            db.add(Alerta(usuario_id=usuario.id, produto_id=produto.id, preco_alvo=alvo))
        db.commit()
        print(f"{len(PRODUTOS)} produtos de demonstração criados.")
        print(f"Entre com {EMAIL_DEMO} / {SENHA_DEMO}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
