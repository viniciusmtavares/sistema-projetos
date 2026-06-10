from database import db
from datetime import datetime

class Levantamento(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    alvo = db.Column(db.String(200))
    tipo_alvo = db.Column(db.String(100))
    pacote = db.Column(db.String(100))
    tipo_projeto = db.Column(db.String(100))
    tipo_execucao = db.Column(db.String(100))
    prioridade = db.Column(db.String(50))

    data_ccs = db.Column(db.Date)
    data_cadastro = db.Column(db.Date)
    entrega_prevista = db.Column(db.Date)

    conta_contrato = db.Column(db.String(50))
    tipo_co = db.Column(db.String(100))
    componente = db.Column(db.String(100))

    nome_cliente = db.Column(db.String(200))
    contato = db.Column(db.String(100))

    municipio = db.Column(db.String(100))
    regional = db.Column(db.String(100))
    zona = db.Column(db.String(100))
    pi = db.Column(db.String(100))

    descricao = db.Column(db.Text)
    acao_projeto = db.Column(db.Text)
    licenciamento = db.Column(db.String(100))

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    anexo_levantamento = db.Column(db.String(255))

    entrega_real = db.Column(db.Date)

    nota_sgo = db.Column(db.String(100))

    bt = db.Column(db.String(100))

    mt = db.Column(db.String(100))

    poste = db.Column(db.String(100))

    material = db.Column(db.Numeric(12, 2))

    mao_de_obra = db.Column(db.Numeric(12, 2))

    valor_total = db.Column(db.Numeric(12, 2))

    status_levantamento = db.Column(db.String(100))

    status_projeto = db.Column(db.String(100))

    motivo_exp = db.Column(db.Text)

    observacoes = db.Column(db.Text)

    anexo_arquivo = db.Column(db.String(255))

    status_licenciamento = db.Column(db.String(50), nullable=True)

    data_envio_licenciamento = db.Column(db.Date, nullable=True)
    data_retorno_licenciamento = db.Column(db.Date, nullable=True)

    numero_licenca = db.Column(db.String(100), nullable=True)
    responsavel_licenciamento = db.Column(db.String(150), nullable=True)

    observacoes_licenciamento = db.Column(db.Text, nullable=True)
    anexo_licenciamento = db.Column(db.String(255), nullable=True)

class Usuario(db.Model):

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(100), nullable=False)

    usuario = db.Column(db.String(50), unique=True, nullable=False)

    perfil = db.Column(db.String(50), default="APPLUS")

    senha = db.Column(db.String(255), nullable=False)

    ativo = db.Column(db.Boolean, default=True)

class HistoricoLevantamento(db.Model):

    __tablename__ = "historico_levantamentos"

    id = db.Column(db.Integer, primary_key=True)

    levantamento_id = db.Column(
        db.Integer,
        db.ForeignKey("levantamento.id"),
        nullable=False
    )

    usuario_nome = db.Column(db.String(100))
    usuario_login = db.Column(db.String(50))
    acao = db.Column(db.String(150))
    detalhes = db.Column(db.Text)

    data_hora = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )