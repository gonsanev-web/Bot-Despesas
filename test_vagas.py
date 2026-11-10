"""Testes da página de vagas (pagina_vagas.py).

Corre-se com: python test_vagas.py. Usa pastas temporárias e um site de teste, por isso não toca
nos teus ficheiros verdadeiros nem no bot. Precisa só do Flask (que já vem no requirements-web.txt).
"""

import os
import tempfile

from flask import Flask

import pagina_vagas

HTTPS = "https://neves716.pythonanywhere.com"  # o cookie só viaja por HTTPS, por isso testamos como no site real

# --- Preparação: pastas temporárias e um site de teste só com as rotas das vagas
pasta = tempfile.mkdtemp()
pasta_vagas = os.path.join(pasta, "dados-vigia")
os.makedirs(pasta_vagas)
ficheiro_senha = os.path.join(pasta, "vagas_senha.txt")
os.environ["VAGAS_PASTA"] = pasta_vagas
os.environ["VAGAS_SENHA_FICHEIRO"] = ficheiro_senha

SENHA = "uma-senha-bem-comprida-123"
PAGINA = "<!doctype html><html><body><script>var x = 1;</script>Vagas de teste ç ã</body></html>"

app = Flask(__name__)
app.register_blueprint(pagina_vagas.vagas)


def escrever(caminho, texto):
    """Ajuda dos testes: grava um ficheiro de texto."""
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


def cliente():
    """Um 'browser' novo (sem cookies) para cada teste."""
    return app.test_client()


def limpar_falhas():
    """Ajuda dos testes: esquece as tentativas erradas, para um teste não bloquear o seguinte."""
    pagina_vagas._falhas.clear()


def entrar(c, senha=SENHA):
    """Ajuda dos testes: põe a palavra-passe no formulário."""
    return c.post("/vagas/entrar", data={"senha": senha}, base_url=HTTPS)


# --- 1. Sem palavra-passe configurada, nada abre
r = cliente().get("/vagas", base_url=HTTPS)
assert r.status_code == 503
assert "configurada" in r.get_data(as_text=True)
r = cliente().get("/vagas/entrar", base_url=HTTPS)
assert r.status_code == 503
escrever(ficheiro_senha, "curta")  # menos de 12 caracteres
assert pagina_vagas.ler_senha() is None
assert cliente().get("/vagas", base_url=HTTPS).status_code == 503
print("sem palavra-passe (ou curta demais): a página recusa-se a abrir")

# --- 2. Com a palavra-passe criada, o formulário aparece e o resto exige entrada
escrever(ficheiro_senha, SENHA + "\n")  # o \n do fim (do editor) é ignorado
assert pagina_vagas.ler_senha() == SENHA
escrever(os.path.join(pasta_vagas, "vagas.html"), PAGINA)

c = cliente()
r = c.get("/vagas", base_url=HTTPS)
assert r.status_code == 303 and r.headers["Location"].endswith("/vagas/entrar")
assert "Vagas de teste" not in r.get_data(as_text=True)
r = c.get("/vagas/", base_url=HTTPS)  # com a barra final também
assert r.status_code == 303
r = c.get("/vagas/entrar", base_url=HTTPS)
assert r.status_code == 200 and 'type="password"' in r.get_data(as_text=True)
assert 'autocomplete="current-password"' in r.get_data(as_text=True)
print("sem cookie: vai para o formulário")

# --- 3. Palavra-passe errada: não entra, não recebe cookie
limpar_falhas()
c = cliente()
r = entrar(c, "palavra-errada-mas-comprida")
assert r.status_code == 403
assert "errada" in r.get_data(as_text=True)
assert "Set-Cookie" not in r.headers
assert c.get("/vagas", base_url=HTTPS).status_code == 303
assert SENHA not in r.get_data(as_text=True)
print("palavra-passe errada: recusada")

# --- 4. Palavra-passe certa: cookie seguro e a página abre
limpar_falhas()
c = cliente()
r = entrar(c)
assert r.status_code == 303 and r.headers["Location"].endswith("/vagas")
cookie = r.headers["Set-Cookie"]
assert "vagas_acesso=" in cookie
assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
assert "Path=/vagas" in cookie
assert "Max-Age=7776000" in cookie  # 90 dias
r = c.get("/vagas", base_url=HTTPS)
assert r.status_code == 200
assert r.get_data(as_text=True) == PAGINA  # a página chega tal e qual, com acentos
assert "Set-Cookie" in r.headers  # cada visita renova o prazo
print("palavra-passe certa: cookie seguro e página aberta")

# --- 5. Cabeçalhos de segurança na página
assert r.headers["Cache-Control"] == "no-store"
assert "noindex" in r.headers["X-Robots-Tag"]
assert r.headers["Referrer-Policy"] == "no-referrer"
assert r.headers["X-Content-Type-Options"] == "nosniff"
csp = r.headers["Content-Security-Policy"]
assert "default-src 'none'" in csp and "script-src 'unsafe-inline'" in csp and "frame-ancestors 'none'" in csp
assert "connect-src" not in csp and "http" not in csp  # nada de ligações a outros sítios
assert "img-src 'self' data:" in csp  # deixa carregar o ícone da app, que é do próprio site
assert r.headers["Content-Type"] == "text/html; charset=utf-8"
print("cabeçalhos de segurança: certos")

# --- 6. Ainda sem página enviada pelo GitHub: mensagem simples, não erro
os.remove(os.path.join(pasta_vagas, "vagas.html"))
r = c.get("/vagas", base_url=HTTPS)
assert r.status_code == 200 and "Ainda não há página" in r.get_data(as_text=True)
escrever(os.path.join(pasta_vagas, "vagas.html"), PAGINA)
print("sem vagas.html: explica em vez de dar erro")

# --- 7. Cookies falsos, expirados ou de outra palavra-passe não valem
agora = 1_800_000_000
bom = pagina_vagas.criar_cookie(SENHA, agora)
assert pagina_vagas.cookie_valido(bom, SENHA, agora)
assert not pagina_vagas.cookie_valido(bom, SENHA, agora + pagina_vagas.VALIDADE_SEGUNDOS + 1)  # expirado
assert not pagina_vagas.cookie_valido(bom, "outra-senha-bem-comprida", agora)  # outra palavra-passe
expira, assinatura = bom.split(".")
assert not pagina_vagas.cookie_valido(f"{int(expira) + 99999}.{assinatura}", SENHA, agora)  # prazo mexido
assert not pagina_vagas.cookie_valido(f"{expira}.{'0' * len(assinatura)}", SENHA, agora)  # assinatura falsa
for lixo in ["", "abc", ".", "123.", ".abc", "²³.abc", "9" * 400 + ".x", None]:
    assert not pagina_vagas.cookie_valido(lixo, SENHA, agora), lixo
c2 = cliente()
c2.set_cookie("vagas_acesso", "9999999999.abcdef", domain="neves716.pythonanywhere.com", path="/vagas")
assert c2.get("/vagas", base_url=HTTPS).status_code == 303
print("cookies falsos, expirados ou de outra palavra-passe: recusados")

# --- 8. Mudar a palavra-passe desliga os aparelhos antigos
c = cliente()
limpar_falhas()
entrar(c)
assert c.get("/vagas", base_url=HTTPS).status_code == 200
escrever(ficheiro_senha, "nova-senha-bem-comprida-456")
assert c.get("/vagas", base_url=HTTPS).status_code == 303
escrever(ficheiro_senha, SENHA)
print("mudar a palavra-passe: os cookies antigos deixam de valer")

# --- 9. Bloqueio depois de muitas tentativas erradas
limpar_falhas()
c = cliente()
for _ in range(pagina_vagas.MAX_FALHAS):
    assert entrar(c, "errada-errada-errada").status_code == 403
r = entrar(c)  # mesmo a certa fica bloqueada durante o bloqueio
assert r.status_code == 429 and "Espera 10 minutos" in r.get_data(as_text=True)
assert "Set-Cookie" not in r.headers
momento = pagina_vagas._falhas[-1]
assert pagina_vagas.bloqueado(momento + 1)
assert not pagina_vagas.bloqueado(momento + pagina_vagas.JANELA_SEGUNDOS + 5)  # passada a janela, desbloqueia
limpar_falhas()
assert entrar(c).status_code == 303
print("muitas tentativas erradas: bloqueia e depois desbloqueia")

# --- 10. Pedido enorme é recusado
r = c.post("/vagas/entrar", data={"senha": "x" * 5000}, base_url=HTTPS)
assert r.status_code == 413
print("pedido enorme: recusado")

# --- 11. O ícone é público (o iPhone vai buscá-lo sem cookie) e o formulário tem as marcas da app
r = cliente().get("/vagas/icone.png", base_url=HTTPS)
assert r.status_code == 200 and r.mimetype == "image/png" and r.data[:8] == b"\x89PNG\r\n\x1a\n"
assert "public" in r.headers["Cache-Control"]
corpo = cliente().get("/vagas/entrar", base_url=HTTPS).get_data(as_text=True)
assert 'rel="apple-touch-icon" href="/vagas/icone.png"' in corpo
assert 'name="apple-mobile-web-app-capable" content="yes"' in corpo
print("ícone público e marcas de app no formulário: certos")

# --- 12. Sair apaga o cookie
limpar_falhas()
c = cliente()
entrar(c)
assert c.get("/vagas", base_url=HTTPS).status_code == 200
r = c.get("/vagas/sair", base_url=HTTPS)
assert r.status_code == 303 and "vagas_acesso=;" in r.headers["Set-Cookie"].replace(" ", "")
assert c.get("/vagas", base_url=HTTPS).status_code == 303
print("sair: apaga o cookie")

# --- 13. O que não é /vagas não existe nesta parte (o bot continua com as suas rotas)
assert cliente().get("/", base_url=HTTPS).status_code == 404  # neste site de teste não há '/'
assert cliente().post("/vagas", base_url=HTTPS).status_code == 405  # só se pode ler, não escrever
print("rotas: só as combinadas")

print("\nTudo certo!")
