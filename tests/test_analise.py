from datetime import date, datetime, timedelta

from app.analise import analisar, black_friday

# Uma data longe da Black Friday, para a regra de datas promocionais não interferir.
AGORA = datetime(2026, 3, 15, 12, 0)


def serie(precos: list[float]) -> list[tuple[datetime, float]]:
    n = len(precos)
    return [(AGORA - timedelta(days=n - 1 - i), p) for i, p in enumerate(precos)]


def test_sem_historico():
    a = analisar([], 100.0, agora=AGORA)
    assert a.veredito == "sem_dados"


def test_preco_no_minimo_do_mes_e_bom_para_comprar():
    precos = [120, 118, 125, 122, 119, 121, 124, 120, 118, 117, 122, 121, 119, 100]
    a = analisar(serie(precos), 100.0, agora=AGORA)
    assert a.veredito == "comprar"
    assert a.titulo == "Bom momento para comprar"
    assert any("menor preço" in m for m in a.motivos)


def test_preco_perto_do_maximo_e_melhor_esperar():
    precos = [100, 98, 101, 99, 100, 97, 102, 100, 99, 98, 101, 100, 99, 125]
    a = analisar(serie(precos), 125.0, agora=AGORA)
    assert a.veredito == "esperar"


def test_preco_estavel_e_neutro():
    a = analisar(serie([50.0] * 14), 50.0, agora=AGORA)
    assert a.veredito == "neutro"


def test_oscilacao_pequena_conta_como_estavel():
    precos = [90.0, 89.5, 90.3, 89.8, 90.1, 89.6, 90.2, 89.9, 90.0, 89.4]
    a = analisar(serie(precos), 89.4, agora=AGORA)
    assert a.veredito == "neutro"


def test_estatisticas():
    a = analisar(serie([200, 180, 160]), 160.0, agora=AGORA)
    assert a.estatisticas.minimo_30d == 160
    assert a.estatisticas.maximo_30d == 200
    assert a.estatisticas.variacao_30d_pct == -20.0


def test_black_friday_e_ultima_sexta_de_novembro():
    assert black_friday(2026) == date(2026, 11, 27)
    assert black_friday(2025) == date(2025, 11, 28)


def test_perto_da_black_friday_sugere_esperar():
    perto_bf = datetime(2026, 11, 10, 12, 0)
    precos = [100, 101, 99, 100, 102, 100, 101, 99, 100, 101, 100, 99, 100, 104]
    pontos = [(perto_bf - timedelta(days=len(precos) - 1 - i), p) for i, p in enumerate(precos)]
    a = analisar(pontos, 104.0, agora=perto_bf)
    assert a.veredito == "esperar"
    assert any("Black Friday" in m for m in a.motivos)
