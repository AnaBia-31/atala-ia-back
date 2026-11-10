"""Motor de análise: diz se é um bom momento para comprar ou se vale esperar.

Esta versão usa REGRAS explicáveis, e não um modelo treinado. Cada regra soma
ou subtrai pontos de um "placar":
    placar > 0  -> a favor de comprar agora
    placar < 0  -> a favor de esperar

A vantagem é que funciona desde o primeiro dia (não precisa de meses de dados
para treinar) e cada decisão vem com os motivos, que aparecem para o usuário.

Para trocar por um modelo de machine learning no futuro, basta manter a mesma
assinatura de `analisar()` e devolver o mesmo objeto `Analise`: o resto da API
não muda. As `Estatisticas` calculadas aqui já são as features que o modelo usaria.
"""

from datetime import date, datetime, timedelta
from statistics import mean, median

from app.schemas import Analise, Estatisticas

# ---- Parâmetros das regras (ajuste aqui para calibrar) ----
JANELA_DIAS = 30
JANELA_TENDENCIA_DIAS = 14
MINIMO_DE_PONTOS = 3
LIMITE_COMPRAR = 0.25
LIMITE_ESPERAR = -0.25
DIAS_ANTES_BLACK_FRIDAY = 21
VARIACAO_MINIMA_RELEVANTE = 0.05  # 5% entre o mínimo e o máximo do mês
# Desconto sobre o preço riscado da página ("de R$ X por R$ Y")
DESCONTO_BOM = 15     # % a partir do qual o desconto, sozinho, já indica compra
DESCONTO_MINIMO = 5   # % abaixo disso o "desconto" é irrelevante

TITULOS = {
    "comprar": "Bom momento para comprar",
    "esperar": "Vale a pena esperar",
    "neutro": "Preço dentro do normal",
    "sem_dados": "Coletando histórico",
}


def black_friday(ano: int) -> date:
    """Última sexta-feira de novembro."""
    dia = date(ano, 11, 30)
    while dia.weekday() != 4:  # 4 = sexta
        dia -= timedelta(days=1)
    return dia


def _dias_ate_black_friday(hoje: date) -> int:
    bf = black_friday(hoje.year)
    if bf < hoje:
        bf = black_friday(hoje.year + 1)
    return (bf - hoje).days


def _tendencia_semanal_pct(pontos: list[tuple[datetime, float]]) -> float | None:
    """Inclinação da reta (mínimos quadrados) em % do preço médio por semana."""
    if len(pontos) < 2:
        return None
    t0 = pontos[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in pontos]
    ys = [p for _, p in pontos]
    mx, my = mean(xs), mean(ys)
    variancia = sum((x - mx) ** 2 for x in xs)
    if variancia == 0 or my == 0:
        return None
    inclinacao_por_dia = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / variancia
    return inclinacao_por_dia * 7 / my * 100


def _pct(a: float, b: float) -> float:
    return (a - b) / b * 100


def _brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def analisar(
    historico: list[tuple[datetime, float]],
    preco_atual: float,
    agora: datetime | None = None,
    preco_original: float | None = None,
) -> Analise:
    """Analisa o histórico de preços de um produto.

    historico: lista de (data da coleta, preço), em qualquer ordem.
    preco_atual: o preço que o usuário está vendo agora.
    preco_original: o preço riscado que a loja mostra ("de R$ X"), se houver.
        Permite dar uma resposta já na primeira visita, quando ainda não há histórico.
    """
    agora = agora or datetime.now()
    historico = sorted(historico)
    janela = [(t, p) for t, p in historico if t >= agora - timedelta(days=JANELA_DIAS)]
    recentes = [(t, p) for t, p in janela if t >= agora - timedelta(days=JANELA_TENDENCIA_DIAS)]
    precos = [p for _, p in janela]

    tendencia = _tendencia_semanal_pct(recentes)
    if preco_original is not None and preco_original <= preco_atual:
        preco_original = None  # "preço original" menor que o atual não é desconto
    desconto = -_pct(preco_atual, preco_original) if preco_original else None
    stats = Estatisticas(
        preco_atual=round(preco_atual, 2),
        minimo_30d=min(precos) if precos else None,
        maximo_30d=max(precos) if precos else None,
        media_30d=round(mean(precos), 2) if precos else None,
        mediana_30d=round(median(precos), 2) if precos else None,
        variacao_30d_pct=round(_pct(preco_atual, precos[0]), 1) if precos else None,
        tendencia_14d_pct=round(tendencia, 1) if tendencia is not None else None,
        pontos_no_historico=len(janela),
        preco_original=preco_original,
        desconto_pct=round(desconto, 1) if desconto is not None else None,
    )

    dias_cobertos = (janela[-1][0] - janela[0][0]).days if janela else 0
    if len(janela) < MINIMO_DE_PONTOS or dias_cobertos < 2:
        return _analise_sem_historico(stats, desconto, agora)

    minimo, maximo, mediana = stats.minimo_30d, stats.maximo_30d, stats.mediana_30d
    placar = 0.0
    motivos: list[str] = []

    # 1) Onde o preço está entre o mínimo e o máximo do mês (0 = no mínimo, 1 = no máximo)
    # Se o preço variou menos que isso no mês, consideramos estável (sem "momento" melhor).
    estavel = (maximo - minimo) / mediana < VARIACAO_MINIMA_RELEVANTE
    no_minimo = not estavel and preco_atual <= minimo * 1.02
    posicao = None if estavel else (preco_atual - minimo) / (maximo - minimo)

    if posicao is None:
        motivos.append("O preço ficou estável nos últimos 30 dias.")
    elif no_minimo:
        placar += 0.5
        if preco_atual <= minimo:
            motivos.append("É o menor preço dos últimos 30 dias.")
        else:
            motivos.append(f"Está a {_pct(preco_atual, minimo):.0f}% do menor preço dos últimos 30 dias ({_brl(minimo)}).")
    elif posicao >= 0.7:
        placar -= 0.4
        motivos.append(f"Está perto do maior preço do mês; já esteve por {_brl(minimo)}.")

    # 2) Comparação com o preço "típico" (mediana)
    diff_mediana = _pct(preco_atual, mediana)
    if diff_mediana <= -5:
        placar += 0.3
        motivos.append(f"Está {abs(diff_mediana):.0f}% abaixo do preço típico ({_brl(mediana)}).")
    elif diff_mediana >= 5:
        placar -= 0.3
        motivos.append(f"Está {diff_mediana:.0f}% acima do preço típico ({_brl(mediana)}).")

    # 3) Tendência recente
    if tendencia is not None and not no_minimo:
        if tendencia <= -3:
            placar -= 0.2
            motivos.append("O preço vem caindo nas últimas semanas e pode baixar mais.")
        elif tendencia >= 3:
            placar += 0.15
            motivos.append("O preço vem subindo; esperar pode sair mais caro.")

    # 4) Desconto anunciado pela loja (peso menor: o histórico é mais confiável)
    if desconto is not None and desconto >= DESCONTO_BOM:
        placar += 0.15
        motivos.append(f"A loja anuncia {desconto:.0f}% de desconto sobre {_brl(preco_original)}.")

    # 5) Datas promocionais
    dias_bf = _dias_ate_black_friday(agora.date())
    if 0 < dias_bf <= DIAS_ANTES_BLACK_FRIDAY and not no_minimo:
        placar -= 0.25
        motivos.append(f"A Black Friday é daqui a {dias_bf} dias; costuma ter descontos.")

    if placar >= LIMITE_COMPRAR:
        veredito = "comprar"
    elif placar <= LIMITE_ESPERAR:
        veredito = "esperar"
    else:
        veredito = "neutro"
        if not motivos:
            motivos.append("O preço está dentro da faixa normal do último mês.")

    # Confiança: mais forte quanto maior o placar e quanto mais dados temos.
    fator_dados = min(1.0, len(janela) / 15)
    confianca = (0.5 + min(abs(placar), 1.0) / 2) * (0.6 + 0.4 * fator_dados)

    return Analise(
        veredito=veredito,
        titulo=TITULOS[veredito],
        confianca=round(min(confianca, 0.95), 2),
        motivos=motivos,
        base="historico",
        estatisticas=stats,
    )


def _analise_sem_historico(stats: Estatisticas, desconto: float | None, agora: datetime) -> Analise:
    """Primeira visita: sem histórico, a única pista é o desconto que a própria página mostra."""
    aviso = "Ainda não temos histórico deste produto; a análise fica mais precisa nos próximos dias."
    if desconto is None or desconto < DESCONTO_MINIMO:
        return Analise(
            veredito="sem_dados",
            titulo=TITULOS["sem_dados"],
            confianca=0.0,
            motivos=["Ainda não temos histórico suficiente deste produto. Volte em alguns dias."],
            base="sem_dados",
            estatisticas=stats,
        )

    motivos = [f"A loja anuncia {desconto:.0f}% de desconto sobre {_brl(stats.preco_original)}."]
    dias_bf = _dias_ate_black_friday(agora.date())
    perto_bf = 0 < dias_bf <= DIAS_ANTES_BLACK_FRIDAY

    if desconto >= DESCONTO_BOM:
        veredito, confianca = "comprar", 0.55
    elif perto_bf:
        veredito, confianca = "esperar", 0.5
        motivos.append(f"O desconto é pequeno e a Black Friday é daqui a {dias_bf} dias.")
    else:
        veredito, confianca = "neutro", 0.4
        motivos.append("É um desconto pequeno; pode valer acompanhar o preço.")
    motivos.append(aviso)
    return Analise(
        veredito=veredito,
        titulo=TITULOS[veredito],
        confianca=confianca,
        motivos=motivos,
        base="desconto_da_pagina",
        estatisticas=stats,
    )
