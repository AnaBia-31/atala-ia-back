"""Tabelas do banco de dados."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Usuario(Base):
    """Conta de usuário. A mesma conta funciona na extensão e no app mobile."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    # Preferências (tela Ajustes). Ficam na conta para valer em todos os aparelhos.
    alerta_queda: Mapped[bool] = mapped_column(Boolean, default=True)
    resumo_semanal: Mapped[bool] = mapped_column(Boolean, default=True)
    analisar_ao_abrir: Mapped[bool] = mapped_column(Boolean, default=True)
    intervalo_verificacao_horas: Mapped[int] = mapped_column(Integer, default=6)
    moeda: Mapped[str] = mapped_column(String(3), default="BRL")


class Produto(Base):
    """Um produto de uma loja, identificado pela URL da página. Compartilhado entre usuários."""

    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    loja: Mapped[str] = mapped_column(String(100))
    titulo: Mapped[str] = mapped_column(String(500))
    imagem_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    moeda: Mapped[str] = mapped_column(String(3), default="BRL")
    # Último preço riscado visto na página ("de R$ X"). Vazio se a loja não mostra desconto.
    preco_original: Mapped[float | None] = mapped_column(Float, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)

    precos: Mapped[list["PrecoHistorico"]] = relationship(
        back_populates="produto", cascade="all, delete-orphan", order_by="PrecoHistorico.coletado_em"
    )


class PrecoHistorico(Base):
    """Um preço visto num momento. É a base de toda a análise."""

    __tablename__ = "precos_historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id", ondelete="CASCADE"), index=True)
    preco: Mapped[float] = mapped_column(Float)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)
    # True = preço inventado para a apresentação (app/simulacao.py), não coletado de verdade.
    simulado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    produto: Mapped[Produto] = relationship(back_populates="precos")


class Visualizacao(Base):
    """Registra que um usuário analisou um produto (tela Histórico)."""

    __tablename__ = "visualizacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id", ondelete="CASCADE"), index=True)
    visto_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    produto: Mapped[Produto] = relationship()


class Alerta(Base):
    """Avisar o usuário quando o produto chegar ao preço-alvo (tela Alertas)."""

    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id", ondelete="CASCADE"), index=True)
    preco_alvo: Mapped[float] = mapped_column(Float)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    disparado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A extensão/app já mostrou a notificação deste disparo?
    notificado: Mapped[bool] = mapped_column(Boolean, default=False)

    produto: Mapped[Produto] = relationship()
