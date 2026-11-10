import pytest

from coletor import extrair_produto, ler_lista, ler_preco

PAGINA_JSONLD = """
<html><head>
<link rel="canonical" href="https://www.kabum.com.br/produto/123/mouse-x">
<meta property="og:image" content="https://img.kabum.com.br/mouse.jpg">
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "Mouse Gamer X",
 "image": ["https://img.kabum.com.br/mouse-grande.jpg"],
 "offers": {"@type": "Offer", "price": 149.99, "priceCurrency": "BRL"}}
</script>
</head><body>
<h1>Mouse Gamer X</h1>
<span class="text-xs line-through">R$ 333,32</span>
<p>R$ 149,99</p>
</body></html>
"""

PAGINA_META = """
<html><head>
<meta property="og:title" content="Teclado Y">
<meta property="og:image" content="/img/teclado.png">
<meta property="product:price:amount" content="1.299,90">
<meta property="og:site_name" content="Loja Exemplo">
</head><body><del>de <b>R$ 1.599,90</b></del></body></html>
"""


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("R$ 1.299,90", 1299.90),
        ("1299.90", 1299.90),
        ("$1,299.90", 1299.90),
        ("R$ 89,9", 89.90),
        ("1.299", 1299.0),
        (319.99, 319.99),
        ("", None),
        ("grátis", None),
        (0, None),
    ],
)
def test_ler_preco(entrada, esperado):
    assert ler_preco(entrada) == esperado


def test_extrai_produto_pelo_jsonld():
    p = extrair_produto(PAGINA_JSONLD, "https://www.kabum.com.br/produto/123/mouse-x?utm_source=x")
    assert p == {
        "url": "https://www.kabum.com.br/produto/123/mouse-x",
        "loja": "KaBuM!",
        "titulo": "Mouse Gamer X",
        "preco": 149.99,
        "preco_original": 333.32,
        "imagem_url": "https://img.kabum.com.br/mouse-grande.jpg",
        "moeda": "BRL",
    }


def test_extrai_produto_pelas_meta_tags():
    p = extrair_produto(PAGINA_META, "https://www.lojaexemplo.com.br/teclado-y")
    assert p["titulo"] == "Teclado Y"
    assert p["preco"] == 1299.90
    assert p["preco_original"] == 1599.90  # texto dentro de <del> com tag aninhada
    assert p["loja"] == "Loja Exemplo"
    assert p["imagem_url"] == "https://www.lojaexemplo.com.br/img/teclado.png"


def test_pagina_sem_preco_nao_e_produto():
    assert extrair_produto("<html><h1>Captcha</h1></html>", "https://www.amazon.com.br/dp/X") is None


def test_preco_riscado_absurdo_e_ignorado():
    html = PAGINA_JSONLD.replace("R$ 333,32", "R$ 9.999,00")  # mais de 3x o preço atual
    assert extrair_produto(html, "https://www.kabum.com.br/p")["preco_original"] is None


def test_ler_lista_ignora_comentarios_e_repetidos(tmp_path):
    arquivo = tmp_path / "lista.txt"
    arquivo.write_text(
        "# comentário\n\nhttps://a.com/1\nhttps://a.com/2  # produto 2\nhttps://a.com/1\nnão é url\n",
        encoding="utf-8",
    )
    assert ler_lista(arquivo) == ["https://a.com/1", "https://a.com/2"]
