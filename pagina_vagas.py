"""A página de vagas (vagas.html) do vigia de estágios, protegida por palavra-passe.

Para que serve: o vigia de estágios corre no GitHub e gera uma página com as vagas. Para a abrires
no iPhone como se fosse uma app, essa página tem de estar num endereço da internet. A tua conta
grátis do PythonAnywhere só permite um site, e esse site já é o do bot de despesas. Por isso a
página vive dentro dele, no endereço /vagas.

Como funciona:
  1. A cada execução, o GitHub envia o vagas.html para a pasta ~/dados-vigia da tua conta.
  2. Quem abre /vagas vê primeiro um formulário com palavra-passe.
  3. Com a palavra-passe certa, o browser fica com um 'cookie' (uma pequena marca) que vale 90 dias.

Nada disto toca no bot de despesas: são rotas à parte (todas começam por /vagas) e o /webhook
fica exatamente igual. A palavra-passe NÃO está no código nem no GitHub: está num ficheiro que
crias tu, na tua conta do PythonAnywhere (~/vagas_senha.txt).
"""

import hashlib
import hmac
import html
import logging
import os
import time
from collections import deque

from flask import Blueprint, Response, redirect, request

# O 'blueprint' é um conjunto de rotas que o servidor_web.py liga ao site com uma só linha
vagas = Blueprint("vagas", __name__)

# --- Valores que podes ajustar -------------------------------------------------------------

# O nome do cookie e quanto tempo ele vale (90 dias; cada visita renova o prazo)
NOME_DO_COOKIE = "vagas_acesso"
VALIDADE_SEGUNDOS = 90 * 24 * 3600

# A palavra-passe tem de ter pelo menos isto, senão a página recusa-se a abrir.
# Palavras-passe curtas podem ser adivinhadas; com 12 ou mais fica muito mais difícil.
MIN_CARACTERES = 12

# Depois de 10 tentativas erradas nos últimos 10 minutos, o formulário bloqueia 10 minutos.
# O bloqueio é para todos (não só para um endereço), por isso quem erra muito também te
# bloqueia a ti durante esse tempo. Para uma página pessoal é um preço razoável.
MAX_FALHAS = 10
JANELA_SEGUNDOS = 10 * 60

# A pasta deste ficheiro: é onde está o ícone da app
PASTA_DO_MODULO = os.path.dirname(os.path.abspath(__file__))


# --- Onde estão os ficheiros ---------------------------------------------------------------


def pasta_das_vagas():
    """A pasta onde o GitHub deposita o vagas.html (por defeito ~/dados-vigia)."""
    return os.environ.get("VAGAS_PASTA") or os.path.join(os.path.expanduser("~"), "dados-vigia")


def ficheiro_da_senha():
    """O ficheiro com a palavra-passe (por defeito ~/vagas_senha.txt, fora do código)."""
    return os.environ.get("VAGAS_SENHA_FICHEIRO") or os.path.join(
        os.path.expanduser("~"), "vagas_senha.txt"
    )


def ler_senha():
    """Lê a palavra-passe do ficheiro. Devolve None se não existir ou se for curta demais.

    Os motivos ficam escritos no 'error log' do site, nunca na resposta ao visitante.
    """
    try:
        # utf-8-sig ignora a marca invisível que alguns editores do Windows põem no início.
        # O strip() tira espaços e a mudança de linha do fim, que o editor acrescenta sozinho.
        with open(ficheiro_da_senha(), encoding="utf-8-sig") as ficheiro:
            senha = ficheiro.read().strip()
    except OSError:
        # Sem o ficheiro, ninguém entra: é mais seguro do que deixar a página aberta
        logging.warning("Página de vagas: falta o ficheiro da palavra-passe (%s)", ficheiro_da_senha())
        return None

    # Uma palavra-passe curta é fácil de adivinhar, por isso recusamos
    if len(senha) < MIN_CARACTERES:
        logging.warning("Página de vagas: a palavra-passe tem menos de %d caracteres", MIN_CARACTERES)
        return None
    return senha


# --- O cookie (a prova de que já puseste a palavra-passe) ----------------------------------

# Guardamos a chave já calculada para não repetir a conta lenta a cada pedido
_chaves = {}


def _chave(senha):
    """Transforma a palavra-passe numa chave para assinar cookies.

    A conta é de propósito lenta (100 mil voltas). Assim, mesmo que alguém apanhe um cookie,
    adivinhar a palavra-passe a partir dele dá muito mais trabalho.
    """
    if senha not in _chaves:
        _chaves[senha] = hashlib.pbkdf2_hmac(
            "sha256", senha.encode("utf-8"), b"vigia-vagas-v1", 100_000
        )
    return _chaves[senha]


def _assinar(senha, expira_texto):
    """A assinatura do cookie: só quem sabe a palavra-passe a consegue calcular."""
    return hmac.new(_chave(senha), expira_texto.encode(), hashlib.sha256).hexdigest()


def criar_cookie(senha, agora):
    """O valor do cookie: 'quando expira' + '.' + assinatura desse momento."""
    expira = str(int(agora) + VALIDADE_SEGUNDOS)
    return f"{expira}.{_assinar(senha, expira)}"


def cookie_valido(valor, senha, agora):
    """True só se a assinatura bate certo com a palavra-passe atual e o prazo não passou."""
    if not valor or not senha:
        return False
    expira_texto, _, assinatura = valor.partition(".")
    # Só aceitamos algarismos normais (isdigit sozinho aceita alguns símbolos estranhos)
    if not (expira_texto.isascii() and expira_texto.isdigit()) or not assinatura:
        return False

    # Calcula a assinatura que o cookie devia ter e compara (sem dar pistas pelo tempo que demora)
    certa = _assinar(senha, expira_texto)
    if not hmac.compare_digest(assinatura.encode("utf-8"), certa.encode("utf-8")):
        return False

    # Assinatura certa: só falta ver se o prazo ainda não passou
    return int(expira_texto) > agora


# --- Bloqueio de tentativas erradas --------------------------------------------------------

# Os momentos das últimas tentativas erradas (só em memória: quando o site reinicia, zera)
_falhas = deque()


def _esquecer_falhas_antigas(agora):
    """Tira da lista as tentativas erradas que já passaram da janela de 10 minutos."""
    # Olha sempre para a tentativa mais antiga: se já passou a janela, tira-a e olha para a seguinte.
    # Para quando a mais antiga ainda é recente ou quando a lista fica vazia (o IndexError).
    while True:
        try:
            if agora - _falhas[0] > JANELA_SEGUNDOS:
                _falhas.popleft()
            else:
                return
        except IndexError:
            return


def bloqueado(agora):
    """True se houve tentativas erradas a mais há pouco tempo."""
    _esquecer_falhas_antigas(agora)
    return len(_falhas) >= MAX_FALHAS


# --- As páginas e os cabeçalhos de segurança -----------------------------------------------

# Regras que dizem ao browser o que a página pode fazer. A página das vagas precisa de correr o
# seu próprio JavaScript, mas não pode ir buscar nada a outros sítios nem ser metida noutra página.
CSP_DA_PAGINA = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
# O formulário de entrada só precisa de estilo e de enviar a palavra-passe para o próprio site.
# O 'img-src self' deixa o browser carregar o ícone da app, que é do próprio site.
CSP_DO_FORMULARIO = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

# O estilo comum das páginas pequenas (entrada, avisos). As cores seguem o modo claro/escuro do telemóvel.
ESTILO_PEQUENO = """
<style>
:root { --papel:#F3F5FA; --superficie:#FFFFFF; --tinta:#0F1B3D; --suave:#55627F;
        --linha:#D6DCE9; --azulejo:#1E3FA0; --sobre:#FFFFFF; --erro:#B3261E; }
@media (prefers-color-scheme: dark) {
  :root { --papel:#0C1325; --superficie:#121B33; --tinta:#E9EDF8; --suave:#9AA7C5;
          --linha:#26324F; --azulejo:#8FA9FF; --sobre:#0C1325; --erro:#FF8A80; }
}
* { box-sizing: border-box; }
body { margin:0; min-height:100vh; display:grid; place-items:center; padding:16px;
       background:var(--papel); color:var(--tinta);
       font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { width:100%; max-width:380px; background:var(--superficie); border:1px solid var(--linha);
       border-radius:16px; padding:24px; }
h1 { margin:0 0 4px; font-size:1.4rem; }
p { margin:8px 0; color:var(--suave); }
label { display:block; margin:16px 0 6px; font-weight:600; color:var(--tinta); }
input { width:100%; padding:12px; font:inherit; color:inherit; background:var(--papel);
        border:1px solid var(--linha); border-radius:10px; }
button { width:100%; margin-top:16px; padding:12px; font:inherit; font-weight:600; border:0;
         border-radius:10px; background:var(--azulejo); color:var(--sobre); }
.erro { color:var(--erro); font-weight:600; }
a { color:var(--azulejo); }
</style>
"""

# O que vai no <head> de todas as páginas pequenas (inclui as marcas para o iPhone tratar a página como app)
CABECA_COMUM = (
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<meta name="robots" content="noindex, nofollow">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-title" content="Vagas">'
    '<link rel="apple-touch-icon" href="/vagas/icone.png">'
)

# O formulário da palavra-passe. O __AVISO__ é trocado pela mensagem de erro, quando há uma.
PAGINA_DE_ENTRADA = (
    '<!doctype html><html lang="pt-PT"><head>' + CABECA_COMUM + "<title>Vagas</title>"
    + ESTILO_PEQUENO
    + """</head><body><main>
<h1>Vigia de vagas</h1>
<p>Página privada. Escreve a palavra-passe para continuar.</p>
__AVISO__
<form method="post" action="/vagas/entrar">
<label for="senha">Palavra-passe</label>
<input id="senha" name="senha" type="password" autocomplete="current-password" required autofocus>
<button type="submit">Entrar</button>
</form>
</main></body></html>"""
)

# Mostrada quando a palavra-passe está certa mas o GitHub ainda não enviou nenhuma página
PAGINA_SEM_VAGAS = (
    '<!doctype html><html lang="pt-PT"><head>' + CABECA_COMUM + "<title>Vagas</title>"
    + ESTILO_PEQUENO
    + """</head><body><main>
<h1>Ainda não há página</h1>
<p>O vigia envia a página a cada execução no GitHub. Se acabaste de ligar tudo, corre-o à mão no
separador Actions e volta aqui dentro de um minuto.</p>
<p><a href="/vagas/sair">Sair</a></p>
</main></body></html>"""
)

# Mostrada quando falta a palavra-passe (ou é curta). Não diz qual é o problema: isso fica no error log.
PAGINA_NAO_CONFIGURADA = (
    '<!doctype html><html lang="pt-PT"><head>' + CABECA_COMUM + "<title>Vagas</title>"
    + ESTILO_PEQUENO
    + """</head><body><main>
<h1>Página ainda não configurada</h1>
<p>Falta acabar a configuração no alojamento. Vê o 'error log' do site para saber o quê.</p>
</main></body></html>"""
)


def _proteger(resposta, csp=CSP_DO_FORMULARIO):
    """Junta à resposta os cabeçalhos de segurança: sem cache, sem pesquisa, sem referências."""
    # no-store: o browser não guarda cópia da página. noindex: os motores de pesquisa ignoram-na.
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Robots-Tag"] = "noindex, nofollow"

    # Não diz a outros sítios de onde vieste, e o browser não "adivinha" o tipo dos ficheiros
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["X-Content-Type-Options"] = "nosniff"

    # As regras do que a página pode carregar (ver as duas listas CSP_ lá em cima)
    resposta.headers["Content-Security-Policy"] = csp
    return resposta


def _pagina(corpo, estado=200, csp=CSP_DO_FORMULARIO):
    """Uma resposta HTML já com os cabeçalhos de segurança."""
    resposta = Response(corpo, status=estado, content_type="text/html; charset=utf-8")
    return _proteger(resposta, csp)


def _dar_cookie(resposta, senha, agora):
    """Põe (ou renova) o cookie de acesso. Só viaja por HTTPS e o JavaScript da página não o vê."""
    resposta.set_cookie(
        NOME_DO_COOKIE,
        criar_cookie(senha, agora),
        max_age=VALIDADE_SEGUNDOS,
        secure=True,
        httponly=True,
        samesite="Lax",
        path="/vagas",
    )
    return resposta


# --- As rotas (endereços) ------------------------------------------------------------------


@vagas.get("/vagas", strict_slashes=False)
def ver_pagina():
    """O endereço principal: mostra a página das vagas a quem já pôs a palavra-passe."""
    agora = time.time()
    senha = ler_senha()
    if senha is None:
        return _pagina(PAGINA_NAO_CONFIGURADA, 503)

    # Sem o cookie certo, manda para o formulário
    if not cookie_valido(request.cookies.get(NOME_DO_COOKIE), senha, agora):
        return _proteger(redirect("/vagas/entrar", 303))

    # Lê o ficheiro que o GitHub enviou. Se ainda não existe, explica em vez de dar erro.
    caminho = os.path.join(pasta_das_vagas(), "vagas.html")
    try:
        with open(caminho, "rb") as ficheiro:
            conteudo = ficheiro.read()
    except OSError:
        return _pagina(PAGINA_SEM_VAGAS)

    # Cada visita renova o prazo do cookie: usando a app, nunca precisas de voltar a entrar
    return _dar_cookie(_pagina(conteudo, csp=CSP_DA_PAGINA), senha, agora)


@vagas.route("/vagas/entrar", methods=["GET", "POST"])
def entrar():
    """O formulário da palavra-passe: GET mostra-o, POST confere a palavra-passe."""
    agora = time.time()
    senha = ler_senha()
    if senha is None:
        return _pagina(PAGINA_NAO_CONFIGURADA, 503)

    if request.method == "GET":
        return _pagina(PAGINA_DE_ENTRADA.replace("__AVISO__", ""))

    # Um formulário de palavra-passe é pequeno; se vier enorme, recusamos logo
    if request.content_length and request.content_length > 4096:
        return _pagina("pedido demasiado grande", 413)

    # Demasiadas tentativas erradas há pouco: nem sequer olha para a palavra-passe
    if bloqueado(agora):
        aviso = '<p class="erro" role="alert">Demasiadas tentativas. Espera 10 minutos.</p>'
        return _pagina(PAGINA_DE_ENTRADA.replace("__AVISO__", aviso), 429)

    # compare_digest compara sem dar pistas pelo tempo que demora
    tentativa = request.form.get("senha", "")
    if hmac.compare_digest(tentativa.encode("utf-8"), senha.encode("utf-8")):
        _falhas.clear()
        return _dar_cookie(_proteger(redirect("/vagas", 303)), senha, agora)

    _falhas.append(agora)
    aviso = '<p class="erro" role="alert">' + html.escape("Palavra-passe errada.") + "</p>"
    return _pagina(PAGINA_DE_ENTRADA.replace("__AVISO__", aviso), 403)


@vagas.get("/vagas/sair")
def sair():
    """Apaga o cookie neste aparelho e volta ao formulário."""
    resposta = _proteger(redirect("/vagas/entrar", 303))
    resposta.delete_cookie(NOME_DO_COOKIE, path="/vagas", secure=True, httponly=True, samesite="Lax")
    return resposta


@vagas.get("/vagas/icone.png")
def icone():
    """O ícone que o iPhone usa quando adicionas a página ao ecrã principal.

    É público de propósito: o iPhone vai buscá-lo sem cookie. É só um desenho, não tem dados.
    """
    try:
        with open(os.path.join(PASTA_DO_MODULO, "vagas_icone.png"), "rb") as ficheiro:
            dados = ficheiro.read()
    except OSError:
        return Response("não existe", status=404)
    return Response(dados, mimetype="image/png", headers={"Cache-Control": "public, max-age=86400"})
