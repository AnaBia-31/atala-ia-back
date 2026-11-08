# Atala.ia: Backend

API em **Python + FastAPI** usada pela extensão do Chrome e pelo app mobile do Atala.ia.
Ela cuida das contas, guarda o histórico de preços e dos alertas e diz se é
**bom momento para comprar** ou se **vale a pena esperar**.

## Rodar localmente

No PowerShell, na raiz deste repositório:

```bash
python -m venv venv
```

```bash
.\venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
```

```bash
python seed.py
```

```bash
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Documentação interativa: http://127.0.0.1:8000/docs (dá para testar todas as rotas por ali)
- Localmente o banco é um arquivo `atala.db` (SQLite), criado sozinho.
- `python seed.py` cria **dados fictícios** para a apresentação: os 4 produtos do protótipo
  com 60 dias de preços inventados e uma conta de demonstração **`demo@atala.ia` / `demo1234`**
  com histórico e alertas. Pode rodar de novo quando quiser: ele recria os dados.

Testes:

```bash
python -m pytest
```

## Login

1. `POST /auth/cadastro` com `{nome, email, senha}` (senha com pelo menos 8 caracteres) ou
   `POST /auth/login` com `{email, senha}`.
2. A resposta traz `access_token` e os dados do `usuario`.
3. A extensão/app guarda o token (extensão: `chrome.storage.local`; mobile: armazenamento
   seguro do aparelho) e envia em toda requisição:
   `Authorization: Bearer <access_token>`.
4. O token vale 30 dias (`ATALA_JWT_VALIDADE_DIAS`). Se a API responder **401**, mande o
   usuário para a tela de login.

A mesma conta funciona na extensão e no celular: histórico, alertas e preferências são da conta.

No `/docs`, faça login, copie o `access_token` e cole no botão **Authorize** para testar as
rotas protegidas.

## Rotas

🔒 = precisa de login. 🔓 = funciona com ou sem login.

| Método | Rota | Tela | O que faz |
|---|---|---|---|
| POST | `/auth/cadastro` | Login | Cria a conta e já devolve o token |
| POST | `/auth/login` | Login | Devolve o token |
| GET | `/usuarios/eu` 🔒 | Ajustes | Dados e preferências da conta |
| PATCH | `/usuarios/eu` 🔒 | Ajustes | Salva preferências: `alerta_queda`, `resumo_semanal`, `analisar_ao_abrir`, `intervalo_verificacao_horas` (6/12/24), `moeda` (BRL/USD/EUR/GBP), `nome` |
| POST | `/produtos/observar` 🔓 | Produto | Envia `{url, loja, titulo, preco, imagem_url?, moeda?}` lido da página. Grava o preço e devolve a análise. Com login, o produto também entra no Histórico |
| GET | `/produtos/{id}` 🔓 | Produto | Produto + análise (+ `alerta_ativo`, se logado) |
| GET | `/produtos/{id}/historico?dias=30` | Produto (gráfico) | Lista de `{preco, coletado_em}` |
| GET | `/historico?dias=7` 🔒 | Histórico | Produtos analisados no período e quanto caíram |
| GET | `/alertas` 🔒 | Alertas | Alertas com preço atual e se já atingiram o alvo |
| POST | `/alertas` 🔒 | Alertas | `{produto_id, preco_alvo}` |
| PATCH | `/alertas/{id}` 🔒 | Alertas | `{ativo}` (liga/desliga) e/ou `{preco_alvo}` |
| DELETE | `/alertas/{id}` 🔒 | Alertas | Remove |
| GET | `/alertas/pendentes` 🔒 | Notificações | Alertas que atingiram o alvo e ainda não viraram notificação. Cada um vem só uma vez |

Exemplo na extensão:

```js
const resp = await fetch(`${API}/produtos/observar`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ url: location.href, loja: "Mercado Livre", titulo, preco }),
});
const { produto, analise } = await resp.json();
// analise.titulo  -> "Bom momento para comprar"
// analise.motivos -> ["Está 7% abaixo do preço típico (R$ 345,87).", ...]
```

## Como a análise funciona

Fica em [`app/analise.py`](app/analise.py). **Não é um modelo treinado**: são regras
explicáveis, que funcionam desde o primeiro dia e sempre mostram os motivos da decisão.

| Regra | Efeito |
|---|---|
| Preço até 2% do mínimo dos últimos 30 dias | a favor de **comprar** |
| Preço na faixa dos 30% mais caros do mês | a favor de **esperar** |
| 5% ou mais abaixo da mediana do mês | a favor de **comprar** |
| 5% ou mais acima da mediana do mês | a favor de **esperar** |
| Preço caindo nas últimas 2 semanas | a favor de **esperar** (pode cair mais) |
| Preço subindo nas últimas 2 semanas | a favor de **comprar** |
| Faltam até 21 dias para a Black Friday | a favor de **esperar** |
| Variação do mês menor que 5% | preço "estável" (sem sinal) |

As regras somam pontos num placar: ≥ 0,25 → `comprar`, ≤ −0,25 → `esperar`, no meio →
`neutro`. Com menos de 3 preços a resposta é `sem_dados`. Os limites ficam no topo do arquivo.

**Próximo passo:** quando houver semanas de preços reais, dá para treinar um classificador
(ex.: LightGBM) que prevê "o preço vai cair ≥ 5% nos próximos 14 dias?". As `Estatisticas` que a
análise já calcula viram as features do modelo, e basta trocar o conteúdo de `analisar()`. As
rotas, a extensão e o app não mudam.

## Colocar no servidor

O repositório tem um `Dockerfile`, então qualquer serviço que rode Docker serve. Exemplo no
**Render**:

1. Crie um **PostgreSQL** (plano gratuito) e copie a *Internal Database URL*.
2. Crie um **Web Service** apontando para este repositório (ele detecta o `Dockerfile`).
3. Em *Environment*, defina as variáveis do [`.env.example`](.env.example):
   - `DATABASE_URL`: a URL do passo 1
   - `ATALA_JWT_SECRET`: um valor aleatório longo. **Obrigatório**: sem ele os logins caem a
     cada reinício. Gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"`
4. Depois do deploy, para ter os dados de demonstração, rode `python seed.py` no *Shell* do serviço.
5. Na extensão, troque `http://127.0.0.1:8000` pela URL do serviço e adicione essa URL em
   `host_permissions` no `manifest.json`.

As tabelas são criadas sozinhas na primeira vez que a API sobe. Se a estrutura das tabelas
mudar depois que houver dados reais, será preciso uma migração (ex.: Alembic). Até a
apresentação, dá para simplesmente apagar e recriar o banco.

## Ainda não feito

- **Limite de tentativas de login** (proteção contra força bruta) e **recuperação de senha**.
- **Notificação push no celular** (ex.: Firebase Cloud Messaging). Por enquanto o app/extensão
  consulta `GET /alertas/pendentes` de tempos em tempos.
- **Coleta automática de preços no servidor.** Hoje o preço só é atualizado quando alguém abre
  o produto pela extensão.
- **Resumo semanal** por e-mail (a preferência já é salva, mas nada é enviado).
