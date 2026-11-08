from conftest import cadastrar


def test_cadastro_devolve_token_e_usuario(client):
    r = client.post("/auth/cadastro", json={"nome": "Ana", "email": "Ana@Example.com", "senha": "senha-forte-123"})
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["usuario"]["email"] == "ana@example.com"  # e-mail guardado em minúsculas
    assert "senha" not in str(corpo["usuario"]).lower()


def test_email_duplicado(client):
    cadastrar(client)
    r = client.post("/auth/cadastro", json={"nome": "Outra", "email": "ANA@example.com", "senha": "outra-senha-1"})
    assert r.status_code == 409


def test_senha_curta_e_email_invalido(client):
    assert client.post("/auth/cadastro", json={"nome": "A", "email": "a@example.com", "senha": "123"}).status_code == 422
    assert client.post("/auth/cadastro", json={"nome": "A", "email": "nao-e-email", "senha": "senha-forte-123"}).status_code == 422


def test_login(client):
    cadastrar(client)
    ok = client.post("/auth/login", json={"email": "ana@example.com", "senha": "senha-forte-123"})
    assert ok.status_code == 200
    token = ok.json()["access_token"]
    eu = client.get("/usuarios/eu", headers={"Authorization": f"Bearer {token}"})
    assert eu.json()["nome"] == "Ana"


def test_login_errado_tem_mesma_mensagem(client):
    cadastrar(client)
    senha_errada = client.post("/auth/login", json={"email": "ana@example.com", "senha": "errada"})
    sem_conta = client.post("/auth/login", json={"email": "ninguem@example.com", "senha": "errada"})
    assert senha_errada.status_code == sem_conta.status_code == 401
    assert senha_errada.json() == sem_conta.json()


def test_token_invalido_ou_ausente(client):
    assert client.get("/usuarios/eu").status_code == 401
    assert client.get("/usuarios/eu", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_preferencias(client, auth):
    r = client.patch("/usuarios/eu", json={"resumo_semanal": False, "intervalo_verificacao_horas": 12, "moeda": "USD"}, headers=auth)
    assert r.status_code == 200
    eu = client.get("/usuarios/eu", headers=auth).json()
    assert eu["resumo_semanal"] is False
    assert eu["intervalo_verificacao_horas"] == 12
    assert eu["moeda"] == "USD"
    assert eu["alerta_queda"] is True  # não mandado, não muda


def test_preferencia_invalida(client, auth):
    assert client.patch("/usuarios/eu", json={"intervalo_verificacao_horas": 7}, headers=auth).status_code == 422
