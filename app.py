from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file, session
from datetime import date, timedelta, datetime
from database import db
from models import Levantamento, Usuario, HistoricoLevantamento
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from io import BytesIO
import os
import pandas as pd

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "sistema_projetos_2026")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:2204@localhost:5432/levantamentos")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "anexos")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ARQUIVO_MUNICIPIOS = os.path.join(BASE_DIR, "MUNICIPIOS_AL.xlsx")
df_municipios = pd.read_excel(ARQUIVO_MUNICIPIOS)
MUNICIPIOS_REGIONAIS = dict(zip(df_municipios["MUNICIPIO"], df_municipios["REGIONAL"]))

db.init_app(app)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def tatico_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("usuario_perfil") != "TATICO":
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated_function

def registrar_historico(levantamento_id, acao, detalhes=None):
    historico = HistoricoLevantamento(
        levantamento_id=levantamento_id,
        usuario_nome=session.get("usuario_nome", "Sistema"),
        usuario_login=session.get("usuario_login", "sistema"),
        acao=acao,
        detalhes=detalhes
    )

    db.session.add(historico)


def buscar_historico(levantamento_id):
    return HistoricoLevantamento.query.filter_by(
        levantamento_id=levantamento_id
    ).order_by(
        HistoricoLevantamento.data_hora.desc()
    ).all()

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None

    if request.method == "POST":
        usuario_digitado = request.form.get("usuario")
        senha_digitada = request.form.get("senha")

        usuario = Usuario.query.filter_by(
            usuario=usuario_digitado,
            ativo=True
        ).first()

        if usuario and check_password_hash(usuario.senha, senha_digitada):
            session["usuario_id"] = usuario.id
            session["usuario_nome"] = usuario.nome
            session["usuario_login"] = usuario.usuario
            session["usuario_perfil"] = usuario.perfil or "APPLUS"
            return redirect(url_for("home"))

        erro = "Usuário ou senha inválidos."

    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/criar_usuario_inicial")
def criar_usuario_inicial():
    usuario_existente = Usuario.query.filter_by(usuario="admin").first()

    if usuario_existente:
        return "Usuário admin já existe."

    novo_usuario = Usuario(
        nome="Administrador",
        usuario="admin",
        senha=generate_password_hash("1234"),
        perfil="TATICO",
        ativo=True
    )

    db.session.add(novo_usuario)
    db.session.commit()

    return "Usuário admin criado com sucesso. Login: admin | Senha: 1234 | Perfil: TATICO"


@app.route("/criar_usuario", methods=["GET", "POST"])
@login_required
@tatico_required
def criar_usuario():
    erro = None
    sucesso = None

    if request.method == "POST":
        nome = request.form.get("nome")
        matricula = request.form.get("matricula")
        perfil = request.form.get("perfil")

        usuario_existente = Usuario.query.filter_by(
            usuario=matricula
        ).first()

        if usuario_existente:
            erro = "Esta matrícula já possui usuário cadastrado."

        else:
            novo_usuario = Usuario(
                nome=nome,
                usuario=matricula,
                senha=generate_password_hash(matricula),
                perfil=perfil,
                ativo=True
            )

            db.session.add(novo_usuario)
            db.session.commit()

            sucesso = f"Usuário criado com sucesso. Login e senha inicial: {matricula}"

    usuarios = Usuario.query.order_by(
        Usuario.nome.asc()
    ).all()

    return render_template(
        "criar_usuario.html",
        usuarios=usuarios,
        erro=erro,
        sucesso=sucesso
    )


@app.route("/alterar_status_usuario/<int:id>")
@login_required
@tatico_required
def alterar_status_usuario(id):
    usuario = Usuario.query.get_or_404(id)

    if usuario.id == session.get("usuario_id"):
        return redirect(url_for("criar_usuario"))

    usuario.ativo = not usuario.ativo

    db.session.commit()

    return redirect(url_for("criar_usuario"))

@app.route("/")
@login_required
def home():

    total_levantamentos = Levantamento.query.count()

    total_projetos = Levantamento.query.filter(
        Levantamento.status_projeto.isnot(None)
    ).count()

    em_levantamento = Levantamento.query.filter(
        db.or_(
            Levantamento.status_levantamento.is_(None),
            Levantamento.status_levantamento == "EM_LEVANTAMENTO"
        ),
        Levantamento.anexo_arquivo.is_(None)
    ).count()

    levantamento_concluido = Levantamento.query.filter(
        Levantamento.anexo_arquivo.isnot(None),
        Levantamento.status_projeto.is_(None),
        Levantamento.status_levantamento != "ANALISE_EXPURGO",
        Levantamento.status_levantamento != "EXPURGADO"
    ).count()

    analise_expurgo = Levantamento.query.filter(
        Levantamento.status_levantamento == "ANALISE_EXPURGO"
    ).count()

    expurgados = Levantamento.query.filter(
        Levantamento.status_levantamento == "EXPURGADO"
    ).count()

    # LEVANTAMENTOS POR REGIONAL
    levantamentos_regionais = db.session.query(
        Levantamento.regional,
        db.func.count(Levantamento.id)
    ).group_by(
        Levantamento.regional
    ).order_by(
        Levantamento.regional
    ).all()

    labels_levantamentos = [
        item[0] or "Sem Regional"
        for item in levantamentos_regionais
    ]

    dados_levantamentos = [
        item[1]
        for item in levantamentos_regionais
    ]

    # PROJETOS POR REGIONAL
    projetos_regionais = db.session.query(
        Levantamento.regional,
        db.func.count(Levantamento.id)
    ).filter(
        Levantamento.status_projeto.isnot(None)
    ).group_by(
        Levantamento.regional
    ).order_by(
        Levantamento.regional
    ).all()

    labels_projetos = [
        item[0] or "Sem Regional"
        for item in projetos_regionais
    ]

    dados_projetos = [
        item[1]
        for item in projetos_regionais
    ]

    return render_template(
        "home.html",
        total_levantamentos=total_levantamentos,
        total_projetos=total_projetos,
        em_levantamento=em_levantamento,
        levantamento_concluido=levantamento_concluido,
        analise_expurgo=analise_expurgo,
        expurgados=expurgados,
        labels_levantamentos=labels_levantamentos,
        dados_levantamentos=dados_levantamentos,
        labels_projetos=labels_projetos,
        dados_projetos=dados_projetos
    )

@app.route("/levantamentos")
@login_required
def levantamentos():
    busca = request.args.get("busca", "")
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    query = Levantamento.query

    query = query.filter(
        db.or_(
            Levantamento.status_levantamento.is_(None),
            Levantamento.status_levantamento.notin_([
                "ANALISE_EXPURGO",
                "EXPURGADO"
            ])
        )
    )

    if busca:
        termo = f"%{busca}%"

        query = query.filter(
            db.or_(
                Levantamento.alvo.ilike(termo),
                Levantamento.tipo_alvo.ilike(termo),
                Levantamento.descricao.ilike(termo),
                Levantamento.acao_projeto.ilike(termo),
                Levantamento.nome_cliente.ilike(termo),
                Levantamento.conta_contrato.ilike(termo),
                Levantamento.municipio.ilike(termo),
                Levantamento.regional.ilike(termo),
                Levantamento.pi.ilike(termo),
                Levantamento.licenciamento.ilike(termo),
                Levantamento.nota_sgo.ilike(termo)
            )
        )

    if status == "EM_LEVANTAMENTO":
        query = query.filter(
            Levantamento.status_projeto.is_(None),
            db.or_(
                Levantamento.status_levantamento.is_(None),
                Levantamento.status_levantamento == "EM_LEVANTAMENTO"
            )
        )

    elif status == "PROJETO_CRIADO":
        query = query.filter(
            Levantamento.status_projeto.isnot(None),
            db.or_(
                Levantamento.status_levantamento.is_(None),
                Levantamento.status_levantamento != "EXPURGADO"
            )
        )

    elif status == "ANALISE_EXPURGO":
        query = query.filter(
            Levantamento.status_levantamento == "ANALISE_EXPURGO"
        )

    elif status == "EXPURGADO":
        query = query.filter(
            Levantamento.status_levantamento == "EXPURGADO"
        )

    pagination = query.order_by(
        Levantamento.id.desc()
    ).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    return render_template(
        "levantamentos.html",
        levantamentos=pagination.items,
        pagination=pagination,
        busca=busca,
        status=status
    )


@app.route("/registrar_levantamento/<int:id>")
@login_required
def registrar_levantamento(id):
    levantamento = Levantamento.query.get_or_404(id)

    return render_template(
        "registrar_levantamento.html",
        levantamento=levantamento
    )


@app.route("/novo")
@login_required
@tatico_required
def novo():
    data_cadastro = date.today()
    entrega_prevista = data_cadastro + timedelta(days=7)
    municipios = sorted(MUNICIPIOS_REGIONAIS.keys())

    return render_template(
        "novo.html",
        data_cadastro=data_cadastro,
        entrega_prevista=entrega_prevista,
        municipios=municipios,
        municipios_regionais=MUNICIPIOS_REGIONAIS
    )


@app.route("/salvar", methods=["POST"])
@login_required
@tatico_required
def salvar():
    data_cadastro = date.today()
    entrega_prevista = data_cadastro + timedelta(days=7)

    data_ccs = request.form.get("data_ccs")
    data_ccs = datetime.strptime(data_ccs, "%Y-%m-%d").date() if data_ccs else None

    novo_levantamento = Levantamento(
        alvo=request.form.get("alvo"),
        tipo_alvo=request.form.get("tipo_alvo"),
        pacote=request.form.get("pacote"),
        tipo_projeto=request.form.get("tipo_projeto"),
        tipo_execucao=request.form.get("tipo_execucao"),
        prioridade=request.form.get("prioridade"),
        data_ccs=data_ccs,
        data_cadastro=data_cadastro,
        entrega_prevista=entrega_prevista,
        conta_contrato=request.form.get("conta_contrato"),
        tipo_co=request.form.get("tipo_co"),
        componente=request.form.get("componente"),
        nome_cliente=request.form.get("nome_cliente"),
        contato=request.form.get("contato"),
        municipio=request.form.get("municipio"),
        regional=request.form.get("regional"),
        zona=request.form.get("zona"),
        pi=request.form.get("pi"),
        descricao=request.form.get("descricao"),
        acao_projeto=request.form.get("acao_projeto"),
        licenciamento=None,
        latitude=float(request.form.get("latitude", 0) or 0),
        longitude=float(request.form.get("longitude", 0) or 0),
        status_levantamento="EM_LEVANTAMENTO"
    )

    arquivo = request.files.get("anexo_levantamento")

    if arquivo and arquivo.filename:
        alvo = secure_filename(request.form.get("alvo") or "SEM_ALVO")
        extensao = os.path.splitext(arquivo.filename)[1]
        nome_arquivo = "LEV_" + alvo + extensao
        caminho_arquivo = os.path.join(app.config["UPLOAD_FOLDER"], nome_arquivo)
        arquivo.save(caminho_arquivo)
        novo_levantamento.anexo_levantamento = nome_arquivo

    db.session.add(novo_levantamento)
    db.session.flush()

    registrar_historico(
        novo_levantamento.id,
        "Solicitação cadastrada",
        "Nova solicitação cadastrada no sistema."
    )

    db.session.commit()

    return redirect(url_for("levantamentos"))

@app.route("/visualizar/<int:id>")
@login_required
def visualizar(id):
    levantamento = Levantamento.query.get_or_404(id)
    historicos = buscar_historico(id)

    return render_template(
        "visualizar.html",
        levantamento=levantamento,
        historicos=historicos
    )

@app.route("/editar_levantamento/<int:id>")
@login_required
@tatico_required
def editar_levantamento(id):
    levantamento = Levantamento.query.get_or_404(id)

    return render_template(
        "editar_levantamento.html",
        levantamento=levantamento
    )

@app.route("/atualizar_levantamento/<int:id>", methods=["POST"])
@login_required
@tatico_required
def atualizar_levantamento(id):
    levantamento = Levantamento.query.get_or_404(id)

    levantamento.alvo = request.form.get("alvo")
    levantamento.tipo_alvo = request.form.get("tipo_alvo")
    levantamento.pacote = request.form.get("pacote")
    levantamento.tipo_projeto = request.form.get("tipo_projeto")
    levantamento.tipo_execucao = request.form.get("tipo_execucao")
    levantamento.prioridade = request.form.get("prioridade")

    data_ccs = request.form.get("data_ccs")
    levantamento.data_ccs = datetime.strptime(data_ccs, "%Y-%m-%d").date() if data_ccs else None

    levantamento.conta_contrato = request.form.get("conta_contrato")
    levantamento.nome_cliente = request.form.get("nome_cliente")
    levantamento.contato = request.form.get("contato")
    levantamento.tipo_co = request.form.get("tipo_co")
    levantamento.componente = request.form.get("componente")
    levantamento.pi = request.form.get("pi")
    levantamento.licenciamento = request.form.get("licenciamento")
    levantamento.descricao = request.form.get("descricao")
    levantamento.acao_projeto = request.form.get("acao_projeto")
    levantamento.municipio = request.form.get("municipio")
    levantamento.regional = request.form.get("regional")
    levantamento.zona = request.form.get("zona")
    levantamento.latitude = float(request.form.get("latitude", 0) or 0)
    levantamento.longitude = float(request.form.get("longitude", 0) or 0)

    arquivo = request.files.get("anexo_levantamento")

    if arquivo and arquivo.filename:
        alvo = secure_filename(levantamento.alvo or "SEM_ALVO")
        extensao = os.path.splitext(arquivo.filename)[1]
        nome_arquivo = "LEV_" + alvo + extensao
        caminho_arquivo = os.path.join(app.config["UPLOAD_FOLDER"], nome_arquivo)
        arquivo.save(caminho_arquivo)
        levantamento.anexo_levantamento = nome_arquivo

    registrar_historico(
        levantamento.id,
        "Solicitação editada",
        "Dados da solicitação foram atualizados."
    )

    db.session.commit()

    return redirect(url_for("levantamentos"))

@app.route("/excluir/<int:id>")
@login_required
@tatico_required
def excluir(id):
    registro = Levantamento.query.get_or_404(id)

    db.session.delete(registro)
    db.session.commit()

    return redirect(url_for("levantamentos"))

@app.route("/salvar_levantamento_campo/<int:id>", methods=["POST"])
@login_required
def salvar_levantamento_campo(id):
    levantamento = Levantamento.query.get_or_404(id)

    expurgo = request.form.get("expurgo")
    levantamento.observacoes = request.form.get("observacoes")

    arquivo = request.files.get("anexo_arquivo")

    nome_arquivo = None

    if arquivo and arquivo.filename:
        descricao = secure_filename(
            levantamento.descricao or levantamento.alvo or "LEVANTAMENTO"
        )

        extensao = os.path.splitext(arquivo.filename)[1]
        nome_arquivo = "CAMPO_" + descricao + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + extensao

        caminho_arquivo = os.path.join(
            app.config["UPLOAD_FOLDER"],
            nome_arquivo
        )

        arquivo.save(caminho_arquivo)

        levantamento.anexo_arquivo = nome_arquivo

    if expurgo == "SIM":
        levantamento.status_levantamento = "ANALISE_EXPURGO"
        levantamento.status_projeto = None

        detalhes = "Parceira informou expurgo no levantamento de campo."

        if nome_arquivo:
            detalhes += f" Anexo: {nome_arquivo}"

        registrar_historico(
            levantamento.id,
            "Levantamento de campo registrado com expurgo",
            detalhes
        )

    else:
        levantamento.status_levantamento = "EM_LEVANTAMENTO"
        levantamento.status_projeto = None

        detalhes = "Parceira concluiu o levantamento de campo sem solicitação de expurgo."

        if nome_arquivo:
            detalhes += f" Anexo: {nome_arquivo}"

        registrar_historico(
            levantamento.id,
            "Levantamento de campo registrado",
            detalhes
        )

    db.session.commit()

    return redirect(url_for("levantamentos"))


@app.route("/confirmar_expurgo/<int:id>")
@login_required
@tatico_required
def confirmar_expurgo(id):
    levantamento = Levantamento.query.get_or_404(id)

    levantamento.status_levantamento = "EXPURGADO"
    levantamento.status_projeto = None

    registrar_historico(
        levantamento.id,
        "Expurgo confirmado",
        "Tático confirmou o expurgo solicitado."
    )

    db.session.commit()

    return redirect(url_for("levantamentos"))


@app.route("/retornar_levantamento/<int:id>")
@login_required
@tatico_required
def retornar_levantamento(id):
    levantamento = Levantamento.query.get_or_404(id)

    levantamento.status_levantamento = "EM_LEVANTAMENTO"
    levantamento.status_projeto = None
    levantamento.motivo_exp = None

    registrar_historico(
        levantamento.id,
        "Expurgo recusado",
        "Tático retornou a solicitação para Em Levantamento."
    )

    db.session.commit()

    return redirect(url_for("levantamentos"))

@app.route("/fazer_projeto/<int:id>")
@login_required
def fazer_projeto(id):
    levantamento = Levantamento.query.get_or_404(id)

    if not levantamento.anexo_arquivo:
        return redirect(url_for("levantamentos"))

    if levantamento.status_levantamento in ["ANALISE_EXPURGO", "EXPURGADO"]:
        return redirect(url_for("levantamentos"))

    return render_template(
        "fazer_projeto.html",
        levantamento=levantamento
    )


@app.route("/salvar_projeto/<int:id>", methods=["POST"])
@login_required
def salvar_projeto(id):
    levantamento = Levantamento.query.get_or_404(id)

    if not levantamento.anexo_arquivo:
        return redirect(url_for("levantamentos"))

    if levantamento.status_levantamento in ["ANALISE_EXPURGO", "EXPURGADO"]:
        return redirect(url_for("levantamentos"))

    entrega_real = request.form.get("entrega_real")
    entrega_real = datetime.strptime(entrega_real, "%Y-%m-%d").date() if entrega_real else None

    levantamento.entrega_real = entrega_real
    levantamento.nota_sgo = request.form.get("nota_sgo")
    levantamento.licenciamento = request.form.get("licenciamento")
    if levantamento.licenciamento == "SIM":

        levantamento.status_licenciamento = "EM_ANALISE"
        levantamento.status_projeto = None
        levantamento.status_levantamento = "CONCLUIDO"

        registrar_historico(
            levantamento.id,
            "Enviado para Licenciamento",
            "Projeto sinalizado com necessidade de licenciamento ambiental."
        )

        db.session.commit()
        return redirect(url_for("licenciamentos"))

    else:
        levantamento.status_licenciamento = None
        levantamento.status_levantamento = "CONCLUIDO"
        levantamento.status_projeto = "PROJETO CRIADO"
    
    levantamento.bt = request.form.get("bt")
    levantamento.mt = request.form.get("mt")
    levantamento.poste = request.form.get("poste")
    levantamento.material = request.form.get("material") or 0
    levantamento.mao_de_obra = request.form.get("mao_de_obra") or 0
    levantamento.valor_total = request.form.get("valor_total") or 0
    levantamento.status_levantamento = "CONCLUIDO"

    observacao_projeto = request.form.get("observacoes")
    arquivo = request.files.get("anexo_projeto") or request.files.get("anexo_arquivo")

    nome_arquivo = None

    if arquivo and arquivo.filename:
        descricao = secure_filename(levantamento.descricao or "SEM_DESCRICAO")
        extensao = os.path.splitext(arquivo.filename)[1]
        nome_arquivo = "PROJETO_" + descricao + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + extensao
        caminho_arquivo = os.path.join(app.config["UPLOAD_FOLDER"], nome_arquivo)
        arquivo.save(caminho_arquivo)
        levantamento.anexo_projeto = nome_arquivo if hasattr(levantamento, "anexo_projeto") else nome_arquivo

    detalhes = "Projeto criado."

    if levantamento.nota_sgo:
        detalhes += f" Nota SGO: {levantamento.nota_sgo}."

    if nome_arquivo:
        detalhes += f" Anexo do projeto: {nome_arquivo}."

    if observacao_projeto:
        detalhes += f" Observações: {observacao_projeto}"

    registrar_historico(
        levantamento.id,
        "Projeto criado",
        detalhes
    )

    db.session.commit()

    return redirect(url_for("projetos"))

@app.route("/projetos")
@login_required
def projetos():
    busca = request.args.get("busca", "")
    licenciamento = request.args.get("licenciamento", "")
    page = request.args.get("page", 1, type=int)

    query = Levantamento.query.filter(
        Levantamento.status_projeto.isnot(None)
    )

    if busca:
        termo = f"%{busca}%"

        query = query.filter(
            db.or_(
                Levantamento.alvo.ilike(termo),
                Levantamento.tipo_alvo.ilike(termo),
                Levantamento.descricao.ilike(termo),
                Levantamento.acao_projeto.ilike(termo),
                Levantamento.nome_cliente.ilike(termo),
                Levantamento.conta_contrato.ilike(termo),
                Levantamento.municipio.ilike(termo),
                Levantamento.regional.ilike(termo),
                Levantamento.pi.ilike(termo),
                Levantamento.licenciamento.ilike(termo),
                Levantamento.nota_sgo.ilike(termo)
            )
        )

    if licenciamento:
        query = query.filter(
            Levantamento.licenciamento == licenciamento
        )

    projetos = query.order_by(
        Levantamento.id.desc()
    ).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    return render_template(
        "projetos.html",
        projetos=projetos,
        busca=busca,
        licenciamento=licenciamento
    )

@app.route("/visualizar_projeto/<int:id>")
@login_required
def visualizar_projeto(id):
    projeto = Levantamento.query.get_or_404(id)
    historicos = buscar_historico(id)

    return render_template(
        "visualizar_projeto.html",
        projeto=projeto,
        historicos=historicos
    )

@app.route("/editar_projeto/<int:id>")
@login_required
def editar_projeto(id):
    projeto = Levantamento.query.get_or_404(id)

    return render_template(
        "editar_projeto.html",
        projeto=projeto
    )

@app.route("/atualizar_projeto/<int:id>", methods=["POST"])
@login_required
def atualizar_projeto(id):
    projeto = Levantamento.query.get_or_404(id)

    entrega_real = request.form.get("entrega_real")
    projeto.entrega_real = datetime.strptime(entrega_real, "%Y-%m-%d").date() if entrega_real else None
    projeto.nota_sgo = request.form.get("nota_sgo")
    projeto.licenciamento = request.form.get("licenciamento")
    projeto.bt = request.form.get("bt")
    projeto.mt = request.form.get("mt")
    projeto.poste = request.form.get("poste")
    projeto.material = request.form.get("material") or 0
    projeto.mao_de_obra = request.form.get("mao_de_obra") or 0
    projeto.valor_total = request.form.get("valor_total") or 0
    projeto.status_levantamento = "CONCLUIDO"
    projeto.status_projeto = "PROJETO CRIADO"
    projeto.motivo_exp = request.form.get("motivo_exp")
    projeto.observacoes = request.form.get("observacoes")

    arquivo = request.files.get("anexo_arquivo")

    nome_arquivo = None

    if arquivo and arquivo.filename:
        descricao = secure_filename(projeto.descricao or "SEM_DESCRICAO")
        extensao = os.path.splitext(arquivo.filename)[1]
        nome_arquivo = "PROJETO_" + descricao + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + extensao
        caminho_arquivo = os.path.join(app.config["UPLOAD_FOLDER"], nome_arquivo)
        arquivo.save(caminho_arquivo)
        projeto.anexo_arquivo = nome_arquivo

    detalhes = "Dados do projeto foram atualizados."

    if nome_arquivo:
        detalhes += f" Novo anexo: {nome_arquivo}"

    registrar_historico(
        projeto.id,
        "Projeto editado",
        detalhes
    )

    db.session.commit()

    return redirect(url_for("projetos"))

@app.route("/excluir_projeto/<int:id>")
@login_required
@tatico_required
def excluir_projeto(id):
    projeto = Levantamento.query.get_or_404(id)

    registrar_historico(
        projeto.id,
        "Projeto excluído",
        "Dados do projeto foram removidos, mantendo a solicitação."
    )

    projeto.entrega_real = None
    projeto.nota_sgo = None
    projeto.bt = None
    projeto.mt = None
    projeto.poste = None
    projeto.material = None
    projeto.mao_de_obra = None
    projeto.valor_total = None
    projeto.status_levantamento = "EM_LEVANTAMENTO"
    projeto.status_projeto = None
    projeto.motivo_exp = None

    db.session.commit()

    return redirect(url_for("projetos"))

@app.route("/visualizar_expurgo/<int:id>")
@login_required
def visualizar_expurgo(id):
    levantamento = Levantamento.query.get_or_404(id)
    historicos = buscar_historico(id)

    return render_template(
        "visualizar_expurgo.html",
        levantamento=levantamento,
        historicos=historicos
    )

@app.route("/baixar_anexo/<path:nome_arquivo>")
@login_required
def baixar_anexo(nome_arquivo):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        nome_arquivo,
        as_attachment=True
    )

@app.route("/exportar_levantamentos")
@login_required
def exportar_levantamentos():
    dados = Levantamento.query.order_by(
        Levantamento.id.desc()
    ).all()

    lista = []

    for item in dados:
        if item.status_levantamento == "ANALISE_EXPURGO":
            status = "ANÁLISE DE EXPURGO"

        elif item.status_levantamento == "EXPURGADO":
            status = "EXPURGADO"

        elif item.status_projeto:
            status = "PROJETO CRIADO"

        elif item.anexo_arquivo:
            status = "LEVANTAMENTO CONCLUÍDO"

        else:
            status = "EM LEVANTAMENTO"

        lista.append({
            "ID": item.id,
            "STATUS": status,
            "ALVO": item.alvo,
            "TIPO ALVO": item.tipo_alvo,
            "PACOTE": item.pacote,
            "TIPO PROJETO": item.tipo_projeto,
            "TIPO EXECUCAO": item.tipo_execucao,
            "PRIORIDADE": item.prioridade,
            "DATA CCS": item.data_ccs,
            "DATA CADASTRO": item.data_cadastro,
            "ENTREGA PREVISTA": item.entrega_prevista,
            "CONTA CONTRATO": item.conta_contrato,
            "NOME CLIENTE": item.nome_cliente,
            "CONTATO": item.contato,
            "TIPO CO": item.tipo_co,
            "COMPONENTE": item.componente,
            "PI": item.pi,
            "LICENCIAMENTO": item.licenciamento,
            "DESCRICAO": item.descricao,
            "ACAO PROJETO": item.acao_projeto,
            "MUNICIPIO": item.municipio,
            "REGIONAL": item.regional,
            "ZONA": item.zona,
            "LATITUDE": item.latitude,
            "LONGITUDE": item.longitude,
            "ANEXO SOLICITACAO": item.anexo_levantamento,
            "ANEXO CAMPO": item.anexo_arquivo
        })

    df = pd.DataFrame(lista)
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Levantamentos"
        )

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="levantamentos.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/exportar_projetos")
@login_required
def exportar_projetos():
    dados = Levantamento.query.filter(
        Levantamento.status_projeto.isnot(None)
    ).order_by(
        Levantamento.id.desc()
    ).all()

    lista = []

    for item in dados:
        lista.append({
            "ID": item.id,
            "ALVO": item.alvo,
            "TIPO ALVO": item.tipo_alvo,
            "PACOTE": item.pacote,
            "TIPO PROJETO": item.tipo_projeto,
            "TIPO EXECUCAO": item.tipo_execucao,
            "PRIORIDADE": item.prioridade,
            "DATA CCS": item.data_ccs,
            "DATA CADASTRO": item.data_cadastro,
            "ENTREGA PREVISTA": item.entrega_prevista,
            "CONTA CONTRATO": item.conta_contrato,
            "NOME CLIENTE": item.nome_cliente,
            "CONTATO": item.contato,
            "TIPO CO": item.tipo_co,
            "COMPONENTE": item.componente,
            "PI": item.pi,
            "LICENCIAMENTO": item.licenciamento,
            "DESCRICAO": item.descricao,
            "ACAO PROJETO": item.acao_projeto,
            "MUNICIPIO": item.municipio,
            "REGIONAL": item.regional,
            "ZONA": item.zona,
            "LATITUDE": item.latitude,
            "LONGITUDE": item.longitude,
            "ENTREGA REAL": item.entrega_real,
            "NOTA SGO": item.nota_sgo,
            "BT": item.bt,
            "MT": item.mt,
            "POSTE": item.poste,
            "MATERIAL": item.material,
            "MAO DE OBRA": item.mao_de_obra,
            "VALOR TOTAL": item.valor_total,
            "STATUS LEVANTAMENTO": item.status_levantamento,
            "STATUS PROJETO": item.status_projeto,
            "MOTIVO EXP": item.motivo_exp,
            "OBSERVACAO": item.observacoes,
            "ANEXO CAMPO": item.anexo_arquivo
        })

    df = pd.DataFrame(lista)
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Projetos"
        )

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="projetos.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/importar_levantamentos")
@login_required
@tatico_required
def importar_levantamentos():
    return render_template("importar_levantamentos.html")

@app.route("/baixar_modelo_levantamentos")
@login_required
@tatico_required
def baixar_modelo_levantamentos():
    colunas = [
        "ALVO", "TIPO ALVO", "PACOTE", "TIPO PROJETO", "TIPO EXECUCAO",
        "PRIORIDADE", "DATA CCS", "CONTA CONTRATO", "NOME CLIENTE",
        "CONTATO", "TIPO CO", "COMPONENTE", "PI", "LICENCIAMENTO",
        "DESCRICAO", "ACAO PROJETO", "MUNICIPIO", "REGIONAL",
        "ZONA", "LATITUDE", "LONGITUDE"
    ]

    df = pd.DataFrame(columns=colunas)
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Modelo"
        )

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="modelo_levantamentos.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/processar_importacao_levantamentos", methods=["POST"])
@login_required
@tatico_required
def processar_importacao_levantamentos():
    arquivo = request.files.get("arquivo_excel")

    if not arquivo:
        return redirect(url_for("importar_levantamentos"))

    df = pd.read_excel(arquivo)

    for _, linha in df.iterrows():
        if pd.isna(linha.get("ALVO")):
            continue

        data_ccs = linha.get("DATA CCS")

        try:
            if pd.notna(data_ccs) and str(data_ccs).strip() != "":
                data_ccs = pd.to_datetime(
                    data_ccs,
                    errors="coerce",
                    dayfirst=True
                )

                data_ccs = data_ccs.date() if pd.notna(data_ccs) else None

            else:
                data_ccs = None

        except:
            data_ccs = None

        latitude = linha.get("LATITUDE")
        longitude = linha.get("LONGITUDE")

        try:
            latitude = float(latitude) if pd.notna(latitude) and str(latitude).strip() != "" else 0
        except:
            latitude = 0

        try:
            longitude = float(longitude) if pd.notna(longitude) and str(longitude).strip() != "" else 0
        except:
            longitude = 0

        data_cadastro = date.today()
        entrega_prevista = data_cadastro + timedelta(days=7)

        novo_levantamento = Levantamento(
            alvo=linha.get("ALVO"),
            tipo_alvo=linha.get("TIPO ALVO"),
            pacote=linha.get("PACOTE"),
            tipo_projeto=linha.get("TIPO PROJETO"),
            tipo_execucao=linha.get("TIPO EXECUCAO"),
            prioridade=linha.get("PRIORIDADE"),
            data_ccs=data_ccs,
            data_cadastro=data_cadastro,
            entrega_prevista=entrega_prevista,
            conta_contrato=linha.get("CONTA CONTRATO"),
            nome_cliente=linha.get("NOME CLIENTE"),
            contato=linha.get("CONTATO"),
            tipo_co=linha.get("TIPO CO"),
            componente=linha.get("COMPONENTE"),
            pi=linha.get("PI"),
            licenciamento=linha.get("LICENCIAMENTO"),
            descricao=linha.get("DESCRICAO"),
            acao_projeto=linha.get("ACAO PROJETO"),
            municipio=linha.get("MUNICIPIO"),
            regional=linha.get("REGIONAL"),
            zona=linha.get("ZONA"),
            latitude=latitude,
            longitude=longitude,
            status_levantamento="EM_LEVANTAMENTO"
        )

        db.session.add(novo_levantamento)
        db.session.flush()

        registrar_historico(
            novo_levantamento.id,
            "Solicitação importada",
            "Solicitação cadastrada por importação de Excel."
        )

    db.session.commit()

    return redirect(url_for("levantamentos"))

@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    usuario = Usuario.query.get_or_404(
        session["usuario_id"]
    )

    erro = None
    sucesso = None

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual")
        nova_senha = request.form.get("nova_senha")
        confirmar_senha = request.form.get("confirmar_senha")

        if not check_password_hash(
            usuario.senha,
            senha_atual
        ):
            erro = "Senha atual incorreta."

        elif nova_senha != confirmar_senha:
            erro = "As novas senhas não conferem."

        else:
            usuario.senha = generate_password_hash(
                nova_senha
            )

            db.session.commit()

            sucesso = "Senha alterada com sucesso."

    return render_template(
        "perfil.html",
        usuario=usuario,
        erro=erro,
        sucesso=sucesso
    )

@app.route("/mapa")
@login_required
def mapa():

    levantamentos = Levantamento.query.all()

    return render_template(
        "mapa.html",
        levantamentos=levantamentos
    )

@app.route("/mapa_projetos")
@login_required
def mapa_projetos():

    projetos = Levantamento.query.filter(
        Levantamento.status_projeto.isnot(None)
    ).all()

    return render_template(
        "mapa_projetos.html",
        projetos=projetos
    )

@app.route("/expurgos")
@login_required
def expurgos():

    busca = request.args.get("busca", "")
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    query = Levantamento.query.filter(
        Levantamento.status_levantamento.in_([
            "ANALISE_EXPURGO",
            "EXPURGADO"
        ])
    )

    if busca:
        termo = f"%{busca}%"

        query = query.filter(
            db.or_(
                Levantamento.alvo.ilike(termo),
                Levantamento.descricao.ilike(termo),
                Levantamento.nome_cliente.ilike(termo),
                Levantamento.conta_contrato.ilike(termo),
                Levantamento.municipio.ilike(termo),
                Levantamento.regional.ilike(termo)
            )
        )

    if status == "ANALISE_EXPURGO":
        query = query.filter(
            Levantamento.status_levantamento == "ANALISE_EXPURGO"
        )

    elif status == "EXPURGADO":
        query = query.filter(
            Levantamento.status_levantamento == "EXPURGADO"
        )

    pagination = query.order_by(
        Levantamento.id.desc()
    ).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    return render_template(
        "expurgos.html",
        expurgos=pagination.items,
        pagination=pagination,
        busca=busca,
        status=status
    )

@app.route("/licenciamentos")
@login_required
def licenciamentos():

    busca = request.args.get("busca", "")
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    query = Levantamento.query.filter(
        Levantamento.status_licenciamento.isnot(None),
        Levantamento.status_projeto.is_(None)
    )

    if busca:
        termo = f"%{busca}%"

        query = query.filter(
            db.or_(
                Levantamento.alvo.ilike(termo),
                Levantamento.descricao.ilike(termo),
                Levantamento.municipio.ilike(termo),
                Levantamento.regional.ilike(termo),
                Levantamento.nome_cliente.ilike(termo),
                Levantamento.conta_contrato.ilike(termo)
            )
        )

    if status:
        query = query.filter(
            Levantamento.status_licenciamento == status
        )

    pagination = query.order_by(
        Levantamento.id.desc()
    ).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    return render_template(
        "licenciamentos.html",
        licenciamentos=pagination.items,
        pagination=pagination,
        busca=busca,
        status=status
    )

@app.route("/fazer_licenciamento/<int:id>")
@login_required
def fazer_licenciamento(id):

    levantamento = Levantamento.query.get_or_404(id)

    return render_template(
        "fazer_licenciamento.html",
        levantamento=levantamento
    )

@app.route("/salvar_licenciamento/<int:id>", methods=["POST"])
@login_required
def salvar_licenciamento(id):

    levantamento = Levantamento.query.get_or_404(id)

    data_envio = request.form.get("data_envio_licenciamento")
    data_retorno = request.form.get("data_retorno_licenciamento")

    levantamento.data_envio_licenciamento = (
        datetime.strptime(data_envio, "%Y-%m-%d").date()
        if data_envio else None
    )

    levantamento.data_retorno_licenciamento = (
        datetime.strptime(data_retorno, "%Y-%m-%d").date()
        if data_retorno else None
    )

    levantamento.responsavel_licenciamento = request.form.get(
        "responsavel_licenciamento"
    )

    levantamento.numero_licenca = request.form.get("numero_licenca")

    levantamento.status_licenciamento = request.form.get(
        "status_licenciamento"
    )

    levantamento.observacoes_licenciamento = request.form.get(
        "observacoes_licenciamento"
    )

    arquivo = request.files.get("anexo_licenciamento")

    if arquivo and arquivo.filename:
        alvo = secure_filename(
            levantamento.alvo or "LICENCIAMENTO"
        )

        extensao = os.path.splitext(arquivo.filename)[1]

        nome_arquivo = "LIC_" + alvo + extensao

        caminho_arquivo = os.path.join(
            app.config["UPLOAD_FOLDER"],
            nome_arquivo
        )

        arquivo.save(caminho_arquivo)

        levantamento.anexo_licenciamento = nome_arquivo

    if levantamento.status_licenciamento == "APROVADO":

        levantamento.status_projeto = "PROJETO CRIADO"

        registrar_historico(
            levantamento.id,
            "Licenciamento aprovado",
            "Licenciamento ambiental aprovado e projeto enviado para Projetos."
        )

        db.session.commit()

        return redirect(url_for("projetos"))

    registrar_historico(
        levantamento.id,
        "Licenciamento atualizado",
        f"Status do licenciamento: {levantamento.status_licenciamento}."
    )

    db.session.commit()

    return redirect(url_for("licenciamentos"))

@app.route("/visualizar_licenciamento/<int:id>")
@login_required
def visualizar_licenciamento(id):

    levantamento = Levantamento.query.get_or_404(id)

    return render_template(
        "visualizar_licenciamento.html",
        levantamento=levantamento
    )

if __name__ == "__main__":
    app.run(debug=False)