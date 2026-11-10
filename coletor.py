"""Coletor automático de preços.

Visita as páginas dos produtos listados em `coletor_produtos.txt`, lê o preço e
envia para a API (POST /produtos/observar), igual a extensão faz. Rodando algumas
vezes por dia, cada produto vai ganhando histórico REAL.

    python coletor.py                                  # envia para a API local
    python coletor.py --api https://SEU-APP.onrender.com
    python coletor.py --simular                        # só mostra o que leu, não envia

Este arquivo usa só o httpx e a biblioteca padrão (não importa o resto do
backend), para rodar leve no GitHub Actions ou no Agendador de Tarefas.

Lojas: funciona com páginas que trazem os dados estruturados do produto (JSON-LD),
como a KaBuM. Amazon, Mercado Livre, Magalu e outras bloqueiam robôs: os preços
delas entram quando alguém abre o produto pela extensão.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

ARQUIVO_PADRAO = Path(__file__).with_name("coletor_produtos.txt")
CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
# Pausa entre uma loja e outra, para não sobrecarregar os sites.
PAUSA_SEGUNDOS = (3.0, 7.0)

LOJAS = {
    "mercadolivre": "Mercado Livre", "mercadolibre": "Mercado Livre", "amazon": "Amazon",
    "shopee": "Shopee", "magazineluiza": "Magazine Luiza", "magalu": "Magazine Luiza",
    "americanas": "Americanas", "casasbahia": "Casas Bahia", "kabum": "KaBuM!",
    "aliexpress": "AliExpress", "netshoes": "Netshoes", "pontofrio": "Ponto",
    "carrefour": "Carrefour", "submarino": "Submarino", "shein": "Shein",
    "pichau": "Pichau", "terabyteshop": "Terabyte",
}
CLASSES_PRECO_RISCADO = re.compile(
    r"line-through|original-price|old-price|list-price|price-from|priceFrom|oldPrice", re.I
)


# ---------------------------------------------------------------------------
# Leitura da página (mesma lógica do src/extrator.js da extensão)
# ---------------------------------------------------------------------------

def ler_preco(valor) -> float | None:
    """'R$ 1.299,90' -> 1299.9 | '1299.90' -> 1299.9 | 319.99 -> 319.99"""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else None
    s = re.sub(r"[^\d.,]", "", str(valor))
    if not s:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s) and not re.fullmatch(r"\d{1,3}\.\d{3}", s):
        pass  # formato "máquina": 1299.90
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
    else:
        s = s.replace(".", "")  # 1.299 (milhar)
    try:
        n = float(s)
    except ValueError:
        return None
    return round(n, 2) if n > 0 else None


class _LeitorHtml(HTMLParser):
    """Junta o que interessa da página: JSON-LD, meta tags, h1, canonical e preços riscados."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.jsonld: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.h1 = ""
        self.riscados: list[str] = []
        self._em_jsonld = False
        self._buffer_jsonld: list[str] = []
        self._em_h1 = False
        self._pilha_riscado: list[str] = []
        self._texto_riscado: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._em_jsonld, self._buffer_jsonld = True, []
        elif tag == "meta":
            chave = a.get("property") or a.get("name") or a.get("itemprop")
            if chave and "content" in a:
                self.meta.setdefault(chave, a["content"])
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href")
        elif tag == "h1" and not self.h1:
            self._em_h1 = True
        if tag in ("s", "del") or CLASSES_PRECO_RISCADO.search(a.get("class", "")):
            if len(self.riscados) < 40:
                self._pilha_riscado.append(tag)
        elif self._pilha_riscado and tag not in ("br", "img", "input", "meta", "link"):
            self._pilha_riscado.append(tag)

    def handle_endtag(self, tag):
        if tag == "script" and self._em_jsonld:
            self.jsonld.append("".join(self._buffer_jsonld))
            self._em_jsonld = False
        elif tag == "h1":
            self._em_h1 = False
        if self._pilha_riscado and tag == self._pilha_riscado[-1]:
            self._pilha_riscado.pop()
            if not self._pilha_riscado:
                texto = " ".join("".join(self._texto_riscado).split())
                if texto:
                    self.riscados.append(texto)
                self._texto_riscado = []

    def handle_data(self, data):
        if self._em_jsonld:
            self._buffer_jsonld.append(data)
        if self._em_h1:
            self.h1 += data
        if self._pilha_riscado:
            self._texto_riscado.append(data)


def _produtos_jsonld(blocos: list[str]) -> list[dict]:
    encontrados = []

    def visitar(no):
        if isinstance(no, list):
            for item in no:
                visitar(item)
        elif isinstance(no, dict):
            tipos = no.get("@type", [])
            tipos = tipos if isinstance(tipos, list) else [tipos]
            if "Product" in tipos or "ProductGroup" in tipos:
                encontrados.append(no)
            if "@graph" in no:
                visitar(no["@graph"])

    for bloco in blocos:
        try:
            visitar(json.loads(bloco))
        except (json.JSONDecodeError, TypeError):
            continue
    return encontrados


def extrair_produto(html: str, url: str) -> dict | None:
    """Devolve {url, loja, titulo, preco, preco_original, imagem_url, moeda} ou None."""
    leitor = _LeitorHtml()
    leitor.feed(html)

    ld = (_produtos_jsonld(leitor.jsonld) or [{}])[0]
    ofertas = ld.get("offers") or ((ld.get("hasVariant") or [{}])[0].get("offers")) or []
    ofertas = ofertas if isinstance(ofertas, list) else [ofertas]
    planas = []
    for o in ofertas:
        if isinstance(o, dict) and "offers" in o:
            internas = o["offers"]
            planas.extend(internas if isinstance(internas, list) else [internas])
        elif isinstance(o, dict):
            planas.append(o)
    oferta = planas[0] if planas else {}

    preco = ler_preco(
        oferta.get("price") or oferta.get("lowPrice") or (oferta.get("priceSpecification") or {}).get("price")
    )
    moeda = oferta.get("priceCurrency")
    titulo = ld.get("name") or ""
    imagem = ld.get("image")
    if isinstance(imagem, list):
        imagem = imagem[0] if imagem else None
    if isinstance(imagem, dict):
        imagem = imagem.get("url") or imagem.get("contentUrl")

    m = leitor.meta
    titulo = titulo or m.get("og:title", "")
    imagem = imagem or m.get("og:image")
    preco = preco or ler_preco(m.get("product:price:amount") or m.get("price"))
    moeda = moeda or m.get("product:price:currency") or m.get("priceCurrency")
    titulo = " ".join((titulo or leitor.h1).split())[:500]
    if not titulo or not preco:
        return None

    preco_original = None
    for texto in leitor.riscados:
        if not re.search(r"\d", texto) or len(texto) > 40:
            continue
        v = ler_preco(texto)
        if v and preco < v < preco * 3:
            preco_original = v
            break

    host = urlsplit(url).hostname or ""
    host = host.removeprefix("www.")
    chave = next((k for k in LOJAS if k in host), None)
    loja = LOJAS[chave] if chave else (m.get("og:site_name") or host)[:100]

    url_final = url
    if leitor.canonical:
        canonica = urljoin(url, leitor.canonical)
        dominio = ".".join(host.split(".")[-2:])
        if (urlsplit(canonica).hostname or "").endswith(dominio):
            url_final = canonica

    imagem_url = urljoin(url, imagem) if imagem else None
    if imagem_url and not imagem_url.startswith(("http://", "https://")):
        imagem_url = None

    return {
        "url": url_final,
        "loja": loja,
        "titulo": titulo,
        "preco": preco,
        "preco_original": preco_original,
        "imagem_url": imagem_url,
        "moeda": (moeda or "BRL").upper()[:3],
    }


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def ler_lista(arquivo: Path) -> list[str]:
    urls = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if linha.startswith(("http://", "https://")):
            urls.append(linha)
    return list(dict.fromkeys(urls))  # sem repetidos, mantendo a ordem


def acordar_api(cliente: httpx.Client, api: str) -> None:
    """Servidores gratuitos "dormem" sem uso; a primeira chamada pode levar ~1 minuto."""
    for tentativa in range(3):
        try:
            cliente.get(f"{api}/", timeout=90)
            return
        except httpx.HTTPError:
            print(f"  API não respondeu (tentativa {tentativa + 1}/3), esperando...")
            time.sleep(10)
    raise SystemExit(f"A API em {api} não respondeu. Confira se o backend está no ar.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta preços e envia para a API do Atala.ia.")
    parser.add_argument("--api", default=os.getenv("ATALA_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--arquivo", type=Path, default=ARQUIVO_PADRAO)
    parser.add_argument("--simular", action="store_true", help="Só mostra o que foi lido, sem enviar")
    args = parser.parse_args()
    api = args.api.rstrip("/")

    urls = ler_lista(args.arquivo)
    if not urls:
        print(f"Nenhuma URL em {args.arquivo}.")
        return 1
    print(f"Coletando {len(urls)} produtos" + (" (simulação)" if args.simular else f" -> {api}"))

    ok, falhas = 0, []
    with httpx.Client(headers=CABECALHOS, follow_redirects=True, timeout=30) as loja, httpx.Client() as cliente_api:
        if not args.simular:
            acordar_api(cliente_api, api)
        for i, url in enumerate(urls):
            if i:
                time.sleep(random.uniform(*PAUSA_SEGUNDOS))
            try:
                resposta = loja.get(url)
                if resposta.status_code != 200:
                    raise RuntimeError(f"a loja respondeu HTTP {resposta.status_code}")
                produto = extrair_produto(resposta.text, str(resposta.url))
                if produto is None:
                    raise RuntimeError("não encontrei título e preço na página (bloqueio ou formato diferente)")
                if not args.simular:
                    r = cliente_api.post(f"{api}/produtos/observar", json=produto, timeout=60)
                    r.raise_for_status()
                riscado = f" (de {produto['preco_original']:.2f})" if produto["preco_original"] else ""
                print(f"  OK   R$ {produto['preco']:>9.2f}{riscado}  {produto['titulo'][:55]}")
                ok += 1
            except Exception as erro:  # noqa: BLE001 - um produto com problema não pode parar a coleta
                falhas.append(url)
                print(f"  FALHA {url[:70]}\n        {erro}")

    print(f"\n{ok} coletados, {len(falhas)} com falha.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
