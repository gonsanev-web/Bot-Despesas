"""Modo alojamento (webhook): é o Telegram que nos entrega cada mensagem.

No PC, o bot.py fica a perguntar ao Telegram "há mensagens novas?" o tempo todo, e por isso
precisa de estar sempre a correr. Aqui é ao contrário: o Telegram faz um pedido a um endereço
da internet sempre que escreves, e este programa só trabalha nesse instante.
Por isso serve para alojamentos gratuitos que não deixam programas ligados 24 horas.

Este ficheiro é o que o site de alojamento (PythonAnywhere) corre.
No PC continuas a usar o bot.py (ou o iniciar.bat).
"""

import asyncio
import hmac
import logging
import os
import threading

from dotenv import load_dotenv
from flask import Flask, request

# O .env fica ao lado deste ficheiro. Indicamos o caminho completo porque no alojamento
# o programa pode arrancar a partir de outra pasta.
PASTA = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PASTA, ".env"))

# Nas contas gratuitas da PythonAnywhere a ligação ao Telegram passa por um 'proxy'
# (um intermediário). Se o .env tiver PROXY_URL, damos o endereço à biblioteca de rede,
# que lê esta variável sozinha. Fora da PythonAnywhere deixa-se PROXY_URL em branco.
proxy = os.getenv("PROXY_URL")
if proxy:
    os.environ.setdefault("HTTPS_PROXY", proxy)

from telegram import Update  # noqa: E402  (tem de vir depois das linhas de cima)
from telegram.ext import ApplicationBuilder  # noqa: E402

import bot  # noqa: E402  (traz a lista de comandos e botões)
import db  # noqa: E402


def ler_do_env(nome):
    """Lê uma variável do .env. Se faltar, para com uma mensagem clara (aparece no 'error log')."""
    valor = os.getenv(nome)
    if not valor:
        raise RuntimeError(f"Falta {nome} no ficheiro .env")
    return valor


# Só quem souber este segredo consegue entregar mensagens ao bot (o Telegram envia-o
# em cada pedido, num cabeçalho). Sem isto, qualquer pessoa podia enviar mensagens falsas.
SEGREDO = ler_do_env("WEBHOOK_SECRET")

# O bot do Telegram, montado uma só vez quando o site arranca.
# updater(None) diz que NÃO vamos perguntar mensagens ao Telegram: elas chegam por webhook.
app_telegram = ApplicationBuilder().token(ler_do_env("BOT_TOKEN")).updater(None).build()
bot.registar_handlers(app_telegram)

# Cria as tabelas e as categorias iniciais (se ainda não existirem) e fecha a ligação.
_ligacao_inicial = db.ligar()
db.criar_tabelas(_ligacao_inicial)
db.semear(_ligacao_inicial)
_ligacao_inicial.close()

# Só tratamos uma mensagem de cada vez (evita duas ligações à base de dados ao mesmo tempo)
_trinco = threading.Lock()
# O número da última mensagem tratada. O Telegram repete uma mensagem se não lhe respondermos
# a tempo, e sem esta guarda a mesma despesa ficava registada duas vezes.
_ultimo_update = 0

# O nome 'application' é o que a PythonAnywhere procura neste tipo de programa
application = Flask(__name__)


async def tratar_update(dados):
    """Entrega uma mensagem (já em formato JSON) ao bot, que responde como no PC.

    'async with' liga o bot ao Telegram no início e desliga no fim.
    """
    async with app_telegram:
        update = Update.de_json(dados, app_telegram.bot)
        await app_telegram.process_update(update)


@application.get("/")
def raiz():
    """Página de teste: abre o endereço no browser e deves ver esta frase."""
    return "O bot de despesas está ligado."


@application.post("/webhook")
def webhook():
    """O Telegram faz um pedido a este endereço por cada mensagem ou botão carregado."""
    global _ultimo_update

    # 1. Confirma que o pedido vem mesmo do Telegram (compare_digest compara sem pistas de tempo)
    recebido = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(recebido.encode(), SEGREDO.encode()):
        return "proibido", 403

    # 2. Lê o conteúdo; todas as mensagens do Telegram trazem um update_id
    dados = request.get_json(silent=True)
    if not dados or "update_id" not in dados:
        return "pedido inválido", 400

    with _trinco:
        # 3. Mensagem repetida: já foi tratada, responde "ok" e ignora
        if dados["update_id"] <= _ultimo_update:
            return "ok"
        _ultimo_update = dados["update_id"]

        # 4. Abre a base de dados só para esta mensagem e fecha no fim
        ligacao = db.ligar()
        app_telegram.bot_data["ligacao"] = ligacao
        try:
            asyncio.run(tratar_update(dados))
        except Exception:
            # Se algo falhar, regista o erro mas responde "ok" na mesma. Se respondêssemos
            # com erro, o Telegram reenviava a mensagem e a despesa ficava duplicada.
            logging.exception("Erro a tratar a mensagem")
        finally:
            ligacao.close()

    return "ok"
