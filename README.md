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
- `python seed.py` cria **histórico de preços simulado** para a apresentação e uma conta de
  demonstração **`demo@atala.ia` / `demo1234`** com histórico e alertas. Veja abaixo.

## Histórico simulado para a apresentação

**Automático:** quando a API vê um produto pela **primeira vez** (nenhum preço salvo), ela gera
**30 dias de preços sintéticos** terminando no preço real de agora. Assim, qualquer produto aberto
na apresentação já mostra gráfico e análise completa.

- Produtos que já têm preço real salvo (ex.: os do coletor) **não** recebem dados sintéticos.
- O perfil da curva acompanha a página: se a loja anuncia desconto grande, a curva é de queda;
  senão, é sorteado (queda, alta ou estável), sempre igual para o mesmo produto.
- Cada preço sintético fica marcado no banco (`simulado = true`). A análise devolve
  `historico_simulado: true`, a extensão avisa "Histórico SIMULADO para demonstração" e desenha
  essa parte do gráfico **tracejada**.
- **Desligar:** variável de ambiente `ATALA_HISTORICO_SIMULADO=0` (no Render, em *Environment*).
- **Apagar todos os preços sintéticos** depois da apresentação (os reais ficam):

  ```bash
  python seed.py --limpar-simulados
  ```

  No servidor, rode do seu PC com `$env:DATABASE_URL="CONNECTION-STRING-DO-NEON"` antes.

**Manual (seed):** para escolher a curva de um produto ou criar a conta demo:

- **Produto que já foi aberto pela extensão** (o jeito mais fácil): abra a página do produto com a
  extensão uma vez e rode:

  ```bash
  python seed.py --url "https://www.amazon.com.br/dp/B0BTYCRJSS" --perfil queda --alvo 120
  ```

  O histórico termina no preço real que a extensão viu. `--perfil` pode ser `queda` (indica
  comprar), `alta` (indica esperar) ou `estavel`. `--alvo` cria um alerta na conta demo.
- **Lista de produtos:** coloque as URLs reais em [`demo_produtos.json`](demo_produtos.json) e
  rode `python seed.py`.

Rodar de novo gera outro histórico. Os preços são **fictícios**: deixem isso claro na apresentação.

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
| POST | `/produtos/observar` 🔓 | Produto | Envia `{url, loja, titulo, preco, preco_original?, imagem_url?, moeda?}` lido da página (`preco_original` é o preço riscado). Grava o preço e devolve a análise. Com login, o produto também entra no Histórico |
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
| A loja anuncia 15% ou mais de desconto (preço riscado) | a favor de **comprar** |
| Faltam até 21 dias para a Black Friday | a favor de **esperar** |
| Variação do mês menor que 5% | preço "estável" (sem sinal) |

As regras somam pontos num placar: ≥ 0,25 → `comprar`, ≤ −0,25 → `esperar`, no meio →
`neutro`. Os limites ficam no topo do arquivo.

**Sem histórico** (menos de 3 preços), a análise usa só o desconto da página: 15% ou mais →
`comprar`; entre 5% e 15% → `neutro` (ou `esperar`, se a Black Friday estiver perto); sem
desconto → `sem_dados`. O campo `base` da resposta diz de onde veio a conclusão
(`historico`, `desconto_da_pagina` ou `sem_dados`).

**Próximo passo:** quando houver semanas de preços reais, dá para treinar um classificador
(ex.: LightGBM) que prevê "o preço vai cair ≥ 5% nos próximos 14 dias?". As `Estatisticas` que a
análise já calcula viram as features do modelo, e basta trocar o conteúdo de `analisar()`. As
rotas, a extensão e o app não mudam.

## Coletor automático de preços

O [`coletor.py`](coletor.py) visita os produtos de [`coletor_produtos.txt`](coletor_produtos.txt),
lê o preço e envia para a API, do mesmo jeito que a extensão. Rodando algumas vezes por dia, cada
produto ganha **histórico real**. Coloquem nessa lista os produtos da apresentação!

```bash
python coletor.py --simular
```

```bash
python coletor.py --api https://atala-ia-back.onrender.com
```

O `--simular` só mostra o que leu, sem enviar nada. Sem `--api`, envia para o backend local.

**Lojas:** funciona com a **KaBuM** (testado com 32 produtos). Amazon, Mercado Livre, Magalu, Casas
Bahia, Pichau e Terabyte bloqueiam robôs: os preços delas entram quando alguém abre o produto
pela extensão.

**Agendamento (escolha um):**

- **GitHub Actions** (recomendado, roda mesmo com o PC desligado): o arquivo
  [`.github/workflows/coletor.yml`](.github/workflows/coletor.yml) roda o coletor 4 vezes por dia
  (23h, 5h, 11h e 17h de Brasília). Confira se o endereço `ATALA_API_URL` nele é o do seu serviço
  no Render. Para rodar na hora: aba **Actions** → **Coletar preços** → **Run workflow**.
- **Agendador de Tarefas do Windows** (reserva, caso a loja bloqueie os servidores do GitHub):

  ```bash
  .\agendar_coletor_windows.ps1 -Api "https://atala-ia-back.onrender.com"
  ```

  Coleta a cada 6 horas enquanto o PC estiver ligado e grava o resultado em `coletor.log`.

## Servidor gratuito (Render + Neon)

- **Render** roda a API (plano gratuito). Ele "dorme" após 15 minutos sem uso: a primeira chamada
  depois disso demora até 1 minuto (a extensão mostra "Acordando o servidor…").
- **Neon** guarda o banco PostgreSQL (plano gratuito, sem data para expirar). O banco gratuito do
  próprio Render é apagado depois de 30 dias, por isso usamos o Neon.

### 1. Banco no Neon

1. Crie uma conta em [neon.tech](https://neon.tech) e um projeto (ex.: `atala`, região São Paulo
   se houver, ou a mais próxima).
2. Em **Connect**, copie a *connection string* (começa com `postgresql://` e termina com
   `?sslmode=require`). Guarde: ela é a senha do banco, **não coloque no código nem no GitHub**.

### 2. API no Render

1. Crie uma conta em [render.com](https://render.com) → **New** → **Web Service**.
2. Escolha **Public Git Repository** e cole `https://github.com/AnaBia-31/atala-ia-back`
   (ou conecte o GitHub da dona do repositório, para o deploy acontecer sozinho a cada push).
3. Configure:
   - **Name:** `atala-ia-back` (vira o endereço `https://atala-ia-back.onrender.com`; se o nome
     estiver ocupado, o Render acrescenta letras, e aí é preciso atualizar a extensão e o
     `coletor.yml`)
   - **Language/Runtime:** Docker · **Instance type:** Free
   - **Environment Variables:**
     - `DATABASE_URL` = a connection string do Neon
     - `ATALA_JWT_SECRET` = um valor aleatório longo, gerado com
       `python -c "import secrets; print(secrets.token_urlsafe(48))"`
4. **Create Web Service** e espere o deploy terminar (alguns minutos). Teste abrindo
   `https://SEU-SERVICO.onrender.com/docs`.

> Alternativa: **New → Blueprint** usa o [`render.yaml`](render.yaml) e já configura tudo (gera a
> `ATALA_JWT_SECRET` sozinho e só pede a `DATABASE_URL`).

### 3. Ligar as peças

1. **Extensão:** em `src/config.js` do repositório da extensão, troque `ATALA_API_URL` pelo endereço
   do Render e recarregue a extensão em `chrome://extensions`.
2. **Coletor:** confira o endereço em `.github/workflows/coletor.yml` e rode uma vez pela aba
   **Actions** para testar.
3. **Dados de demonstração (opcional):** o plano gratuito do Render não tem terminal, então rode o
   seed do seu PC apontando para o Neon:

   ```bash
   $env:DATABASE_URL="COLE-A-CONNECTION-STRING-DO-NEON"; python seed.py
   ```

As tabelas são criadas sozinhas na primeira vez que a API sobe. Se a estrutura das tabelas
mudar depois que houver dados reais, será preciso uma migração (ex.: Alembic). Até a
apresentação, dá para simplesmente apagar e recriar o banco.

## Ainda não feito

- **Limite de tentativas de login** (proteção contra força bruta) e **recuperação de senha**.
- **Notificação push no celular** (ex.: Firebase Cloud Messaging). Por enquanto o app consulta
  `GET /alertas/pendentes` de tempos em tempos.
- **Coleta de lojas que bloqueiam robôs** (Amazon, Mercado Livre...). O Mercado Livre tem uma
  API oficial, mas ela exige cadastrar um aplicativo no portal de desenvolvedores e usar token.
- **Resumo semanal** por e-mail (a preferência já é salva, mas nada é enviado).
- **Proteção da rota `/produtos/observar`**: hoje qualquer um pode enviar preços para ela.
