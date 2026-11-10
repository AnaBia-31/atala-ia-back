import pytest

from conftest import cadastrar


def observar(client, preco, headers=None, url="https://www.loja.com/produto-x?utm_source=abc"):
    return client.post(
        "/produtos/observar",
        json={"url": url, "loja": "Loja", "titulo": "Produto X", "preco": preco},
        headers=headers or {},
    )


def test_observar_sem_login_funciona(client):
    r = observar(client, 99.9)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["produto"]["url"] == "https://www.loja.com/produto-x"  # sem ?utm
    assert corpo["analise"]["veredito"] == "sem_dados"
    assert corpo["alerta_ativo"] is False


def test_mesmo_produto_com_parametros_diferentes_nao_duplica(client):
    a = observar(client, 100).json()["produto"]["id"]
    b = observar(client, 90, url="https://www.loja.com/produto-x#avaliacoes").json()["produto"]["id"]
    assert a == b
    hist = client.get(f"/produtos/{a}/historico").json()
    assert [p["preco"] for p in hist] == [100, 90]


def test_preco_repetido_nao_grava_ponto_duplicado(client):
    pid = observar(client, 100).json()["produto"]["id"]
    observar(client, 100)
    assert len(client.get(f"/produtos/{pid}/historico").json()) == 1


def test_historico_do_usuario(client, auth):
    observar(client, 120, auth)
    observar(client, 100, auth)
    r = client.get("/historico", headers=auth).json()
    assert r["produtos_analisados"] == 1
    assert r["economia_identificada"] == 20
    assert r["itens"][0]["variacao_30d_pct"] == pytest.approx(-16.7)


def test_historico_e_separado_por_usuario(client, auth):
    observar(client, 120, auth)
    outro = cadastrar(client, email="bia@example.com")
    assert client.get("/historico", headers=outro).json()["produtos_analisados"] == 0


def test_historico_exige_login(client):
    assert client.get("/historico").status_code == 401


def test_fluxo_de_alerta(client, auth):
    pid = observar(client, 300, auth).json()["produto"]["id"]
    r = client.post("/alertas", json={"produto_id": pid, "preco_alvo": 250}, headers=auth)
    assert r.status_code == 201
    alerta_id = r.json()["id"]
    assert r.json()["atingido"] is False
    assert client.get(f"/produtos/{pid}", headers=auth).json()["alerta_ativo"] is True
    assert client.get("/alertas/pendentes", headers=auth).json() == []

    observar(client, 240)  # qualquer pessoa (até sem login) viu o preço cair abaixo do alvo
    pendentes = client.get("/alertas/pendentes", headers=auth).json()
    assert [a["id"] for a in pendentes] == [alerta_id]
    assert client.get("/alertas/pendentes", headers=auth).json() == []  # só notifica uma vez

    r = client.patch(f"/alertas/{alerta_id}", json={"ativo": False}, headers=auth)
    assert r.json()["ativo"] is False
    assert client.get(f"/produtos/{pid}", headers=auth).json()["alerta_ativo"] is False

    assert client.delete(f"/alertas/{alerta_id}", headers=auth).status_code == 204
    assert client.get("/alertas", headers=auth).json() == []


def test_alerta_de_outro_usuario_nao_e_acessivel(client, auth):
    pid = observar(client, 300).json()["produto"]["id"]
    alerta_id = client.post("/alertas", json={"produto_id": pid, "preco_alvo": 250}, headers=auth).json()["id"]
    outro = cadastrar(client, email="bia@example.com")
    assert client.delete(f"/alertas/{alerta_id}", headers=outro).status_code == 404
    assert client.patch(f"/alertas/{alerta_id}", json={"ativo": False}, headers=outro).status_code == 404
    assert client.get("/alertas", headers=outro).json() == []


def test_alertas_exigem_login(client):
    assert client.get("/alertas").status_code == 401


def test_produto_inexistente(client):
    assert client.get("/produtos/999").status_code == 404


def test_observar_com_preco_riscado_responde_na_primeira_visita(client):
    r = client.post(
        "/produtos/observar",
        json={"url": "https://loja.com/p", "loja": "Loja", "titulo": "P", "preco": 75, "preco_original": 100},
    ).json()
    assert r["analise"]["veredito"] == "comprar"
    assert r["analise"]["estatisticas"]["desconto_pct"] == 25.0
