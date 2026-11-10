import random

import pytest
from sqlalchemy import create_engine, inspect, text

from app import config
from app.database import migrar_colunas_novas
from app.simulacao import DIAS_SIMULADOS, escolher_perfil, gerar_precos


@pytest.fixture()
def simulacao_ligada(monkeypatch):
    monkeypatch.setattr(config, "HISTORICO_SIMULADO", True)


def observar(client, preco=200.0, url="https://www.loja.com/produto-novo", **extra):
    corpo = {"url": url, "loja": "Loja", "titulo": "Produto novo", "preco": preco, **extra}
    r = client.post("/produtos/observar", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def test_produto_novo_ganha_30_dias_simulados(client, simulacao_ligada):
    r = observar(client, 200.0)
    a = r["analise"]
    assert a["base"] == "historico"
    assert a["historico_simulado"] is True
    assert a["veredito"] in ("comprar", "esperar", "neutro")

    pontos = client.get(f"/produtos/{r['produto']['id']}/historico?dias=60").json()
    assert len(pontos) == DIAS_SIMULADOS + 1
    assert all(p["simulado"] for p in pontos[:-1])
    assert pontos[-1]["simulado"] is False
    assert pontos[-1]["preco"] == 200.0  # o último ponto é o preço real


def test_simulacao_acontece_uma_vez_so(client, simulacao_ligada):
    pid = observar(client, 200.0)["produto"]["id"]
    observar(client, 190.0)
    pontos = client.get(f"/produtos/{pid}/historico?dias=60").json()
    assert len(pontos) == DIAS_SIMULADOS + 2
    assert [p["simulado"] for p in pontos[-2:]] == [False, False]


def test_produto_com_preco_real_nao_recebe_simulacao(client, monkeypatch):
    monkeypatch.setattr(config, "HISTORICO_SIMULADO", False)
    pid = observar(client, 200.0)["produto"]["id"]  # já tem histórico real
    monkeypatch.setattr(config, "HISTORICO_SIMULADO", True)
    r = observar(client, 180.0)
    pontos = client.get(f"/produtos/{pid}/historico?dias=60").json()
    assert len(pontos) == 2
    assert not any(p["simulado"] for p in pontos)
    assert r["analise"]["historico_simulado"] is False


def test_desligado_nao_gera_nada(client):
    r = observar(client, 200.0)
    assert r["analise"]["veredito"] == "sem_dados"
    assert r["analise"]["historico_simulado"] is False


def test_desconto_grande_gera_curva_de_queda(client, simulacao_ligada):
    r = observar(client, 100.0, preco_original=180.0)
    pontos = client.get(f"/produtos/{r['produto']['id']}/historico?dias=60").json()
    assert pontos[0]["preco"] > pontos[-1]["preco"]
    assert r["analise"]["veredito"] == "comprar"


def test_escolher_perfil():
    assert escolher_perfil("https://a.com/x", 100, 150) == "queda"
    perfil = escolher_perfil("https://a.com/x", 100, None)
    assert perfil in ("queda", "alta", "estavel")
    assert escolher_perfil("https://a.com/x", 100, None) == perfil  # sempre o mesmo para a mesma URL


def test_gerar_precos_termina_no_preco_final():
    precos = gerar_precos(99.9, "alta", random.Random(1), 31)
    assert len(precos) == 31
    assert precos[-1] == 99.9
    assert precos[0] < 99.9


def test_migracao_adiciona_coluna_em_banco_antigo():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE precos_historico (id INTEGER PRIMARY KEY, produto_id INTEGER, preco FLOAT, coletado_em DATETIME)"))
        c.execute(text("INSERT INTO precos_historico (produto_id, preco, coletado_em) VALUES (1, 10.0, '2026-11-01')"))
    migrar_colunas_novas(engine)
    assert "simulado" in {col["name"] for col in inspect(engine).get_columns("precos_historico")}
    with engine.connect() as c:
        assert c.execute(text("SELECT simulado FROM precos_historico")).scalar() in (0, False)
    migrar_colunas_novas(engine)  # rodar de novo não pode dar erro
