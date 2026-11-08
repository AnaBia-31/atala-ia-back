"""Formato dos dados que entram e saem da API (validados pelo Pydantic)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

Veredito = Literal["comprar", "esperar", "neutro", "sem_dados"]
Moeda = Literal["BRL", "USD", "EUR", "GBP"]


# ---------- Contas ----------

class CadastroEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)


class LoginEntrada(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class UsuarioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    criado_em: datetime
    alerta_queda: bool
    resumo_semanal: bool
    analisar_ao_abrir: bool
    intervalo_verificacao_horas: int
    moeda: str


class TokenSaida(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    usuario: UsuarioSaida


class PreferenciasEntrada(BaseModel):
    """Botão "Salvar alterações" da tela Ajustes. Só manda o que mudou."""

    nome: str | None = Field(default=None, min_length=1, max_length=100)
    alerta_queda: bool | None = None
    resumo_semanal: bool | None = None
    analisar_ao_abrir: bool | None = None
    intervalo_verificacao_horas: Literal[6, 12, 24] | None = None
    moeda: Moeda | None = None


# ---------- Produtos ----------

class ObservacaoEntrada(BaseModel):
    """O que a extensão envia ao abrir a página de um produto."""

    url: HttpUrl
    loja: str = Field(min_length=1, max_length=100, examples=["Mercado Livre"])
    titulo: str = Field(min_length=1, max_length=500)
    preco: float = Field(gt=0)
    imagem_url: HttpUrl | None = None
    moeda: str = Field(default="BRL", min_length=3, max_length=3)


class Estatisticas(BaseModel):
    preco_atual: float
    minimo_30d: float | None
    maximo_30d: float | None
    media_30d: float | None
    mediana_30d: float | None
    variacao_30d_pct: float | None = Field(description="Ex.: -14.0 = caiu 14% no mês")
    tendencia_14d_pct: float | None = Field(description="Inclinação recente, em % do preço por semana")
    pontos_no_historico: int


class Analise(BaseModel):
    veredito: Veredito
    titulo: str = Field(description="Frase curta para o card, ex.: 'Bom momento para comprar'")
    confianca: float = Field(ge=0, le=1)
    motivos: list[str]
    estatisticas: Estatisticas


class ProdutoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    loja: str
    titulo: str
    imagem_url: str | None
    moeda: str
    atualizado_em: datetime


class ProdutoDetalhe(BaseModel):
    produto: ProdutoSaida
    analise: Analise
    alerta_ativo: bool = False


class PontoHistorico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    preco: float
    coletado_em: datetime


# ---------- Histórico do usuário ----------

class ItemHistorico(BaseModel):
    produto: ProdutoSaida
    preco_atual: float
    variacao_30d_pct: float | None
    visto_em: datetime


class ResumoHistorico(BaseModel):
    produtos_analisados: int
    economia_identificada: float = Field(description="Soma de quanto os produtos caíram no período (R$)")
    itens: list[ItemHistorico]


# ---------- Alertas ----------

class AlertaEntrada(BaseModel):
    produto_id: int
    preco_alvo: float = Field(gt=0)


class AlertaAtualizacao(BaseModel):
    preco_alvo: float | None = Field(default=None, gt=0)
    ativo: bool | None = None


class AlertaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    produto: ProdutoSaida
    preco_alvo: float
    preco_atual: float | None = None
    ativo: bool
    atingido: bool = False
    criado_em: datetime
    disparado_em: datetime | None
