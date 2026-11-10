"""Gera HISTÓRICO DE PREÇOS SIMULADO para a apresentação.

Sem histórico, a análise de um produto novo só consegue dizer "Coletando histórico"
(ou usar o desconto que a página mostra). Este script inventa 60 dias de preços
para alguns produtos e cria uma conta de demonstração com histórico e alertas.
Os preços são FICTÍCIOS: deixe isso claro na apresentação.

Dois jeitos de usar:

1) Lista de produtos (demo_produtos.json):
       python seed.py
   Troque as URLs do arquivo pelas URLs REAIS dos produtos que vocês vão abrir
   na apresentação. Campos: url (obrigatório), titulo, loja, preco_final,
   perfil ("queda", "alta" ou "estavel") e preco_alvo (alerta da conta demo).

2) Um produto que já foi aberto pela extensão:
       python seed.py --url "https://www.mercadolivre.com.br/..." --perfil queda
   Usa o título, a imagem e o preço que a extensão registrou e cria o histórico
   simulado terminando nesse preço.

Rodar de novo apaga o histórico desses produtos e gera outro.
"""

import argparse
import json
import random
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select

from app.database import SessionLocal, criar_tabelas
from app.models import Alerta, PrecoHistorico, Produto, Usuario, Visualizacao, agora
from app.seguranca import gerar_hash_senha
from app.servicos import normalizar_url

# Conta só para a apresentação. Não use essa senha em nenhum outro lugar.
EMAIL_DEMO = "demo@atala.ia"
SENHA_DEMO = "demo1234"
ARQUIVO_PRODUTOS = Path(__file__).with_name("demo_produtos.json")
DIAS = 60

# Preço do início do período em relação ao preço final, para cada perfil.
INICIO_POR_PERFIL = {"queda": 1.30, "alta": 0.80, "estavel": 1.0}


def gerar_precos(final: float, perfil: str, rng: random.Random) -> list[float]:
    """Caminho de preços com ruído e uma promoção curta no meio, terminando em `final`."""
    base = final * INICIO_POR_PERFIL[perfil]
    precos = []
    for i in range(DIAS):
        progresso = i / (DIAS - 1)
        preco = base + (final - base) * progresso
        ruido = 0.01 if perfil == "estavel" else 0.035
        preco *= 1 + rng.uniform(-ruido, ruido)
        if perfil != "estavel" and DIAS * 0.4 < i < DIAS * 0.45:  # promoção relâmpago
            preco *= 0.88
        precos.append(round(preco, 2))
    precos[-1] = round(final, 2)
    return precos


def conta_demo(db) -> Usuario:
    usuario = db.scalars(select(Usuario).where(Usuario.email == EMAIL_DEMO)).first()
    if usuario is None:
        usuario = Usuario(nome="Conta Demo", email=EMAIL_DEMO, senha_hash=gerar_hash_senha(SENHA_DEMO))
        db.add(usuario)
        db.flush()
    return usuario


def simular(db, item: dict, usuario: Usuario, rng: random.Random, posicao: int) -> None:
    url = normalizar_url(item["url"])
    perfil = item.get("perfil") or "queda"
    if perfil not in INICIO_POR_PERFIL:
        raise SystemExit(f"Perfil inválido '{perfil}'. Use: {', '.join(INICIO_POR_PERFIL)}")

    produto = db.scalars(select(Produto).where(Produto.url == url)).first()
    ultimo_real = None
    if produto is None:
        if "titulo" not in item or "preco_final" not in item:
            raise SystemExit(
                f"O produto {url} ainda não foi aberto pela extensão. Abra a página dele com a "
                "extensão primeiro, ou informe titulo e preco_final no demo_produtos.json."
            )
        produto = Produto(url=url, titulo=item["titulo"], loja=item.get("loja", "Loja"))
        db.add(produto)
        db.flush()
    else:
        ultimo_real = db.scalars(
            select(PrecoHistorico.preco)
            .where(PrecoHistorico.produto_id == produto.id)
            .order_by(PrecoHistorico.coletado_em.desc())
            .limit(1)
        ).first()

    # Preço final: o que a extensão viu de verdade (se houver); senão, o do arquivo.
    final = ultimo_real or item.get("preco_final")
    if not final:
        raise SystemExit(f"Sem preço para {url}: abra o produto pela extensão ou informe preco_final.")

    db.execute(delete(PrecoHistorico).where(PrecoHistorico.produto_id == produto.id))
    hoje = agora()
    for d, preco in enumerate(gerar_precos(final, perfil, rng)):
        horas = 0 if d == DIAS - 1 else rng.randint(1, 5)
        coletado = hoje - timedelta(days=DIAS - 1 - d, hours=horas)
        db.add(PrecoHistorico(produto_id=produto.id, preco=preco, coletado_em=coletado))

    db.execute(
        delete(Visualizacao).where(Visualizacao.produto_id == produto.id, Visualizacao.usuario_id == usuario.id)
    )
    db.add(Visualizacao(usuario_id=usuario.id, produto_id=produto.id, visto_em=hoje - timedelta(days=posicao)))
    if item.get("preco_alvo"):
        db.execute(delete(Alerta).where(Alerta.produto_id == produto.id, Alerta.usuario_id == usuario.id))
        db.add(Alerta(usuario_id=usuario.id, produto_id=produto.id, preco_alvo=float(item["preco_alvo"])))
    print(f"  {produto.titulo[:50]:<50} {perfil:<8} termina em R$ {final:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera histórico de preços SIMULADO para a apresentação.")
    parser.add_argument("--url", help="URL de um produto (de preferência já aberto pela extensão)")
    parser.add_argument("--perfil", default="queda", choices=list(INICIO_POR_PERFIL))
    parser.add_argument("--alvo", type=float, help="Preço-alvo do alerta da conta demo")
    args = parser.parse_args()

    if args.url:
        itens = [{"url": args.url, "perfil": args.perfil, "preco_alvo": args.alvo}]
    else:
        itens = json.loads(ARQUIVO_PRODUTOS.read_text(encoding="utf-8"))

    criar_tabelas()
    rng = random.Random(42)  # sempre gera os mesmos dados
    db = SessionLocal()
    try:
        usuario = conta_demo(db)
        print("Histórico simulado gerado:")
        for i, item in enumerate(itens):
            simular(db, item, usuario, rng, i)
        db.commit()
        print(f"\nConta demo: {EMAIL_DEMO} / {SENHA_DEMO}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
