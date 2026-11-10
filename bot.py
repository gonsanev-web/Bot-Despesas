"""Ponto de entrada no PC: arranca o bot e liga cada comando e botão à sua função."""

import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import db
import handlers

load_dotenv()  # lê o .env (BOT_TOKEN e MEU_ID)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
# Evita que o token apareça nos registos
logging.getLogger("httpx").setLevel(logging.WARNING)

# O menu de comandos que aparece no Telegram ao escrever "/"
COMANDOS = [
    BotCommand("semana", "Gastos da semana, um a um"),
    BotCommand("hoje", "Gastos de hoje"),
    BotCommand("mes", "Gastos do mês, um a um"),
    BotCommand("comparar", "Compara a semana ou o mês com o anterior"),
    BotCommand("lista", "Movimentos de uma categoria"),
    BotCommand("desfazer", "Apaga o último registo"),
    BotCommand("corrigir", "Muda a categoria do último registo"),
    BotCommand("orcamento", "Define o orçamento mensal"),
    BotCommand("avisar", "Define a percentagem do aviso"),
    BotCommand("temas", "Categorias e palavras conhecidas"),
    BotCommand("exportar", "Ficheiro CSV com tudo"),
    BotCommand("limpar", "Apaga todas as despesas"),
    BotCommand("ajuda", "Lista de comandos"),
]


async def depois_de_iniciar(app):
    """Corre uma vez quando o bot arranca: põe o menu de comandos no Telegram."""
    await app.bot.set_my_commands(COMANDOS)


def registar_handlers(app):
    """Liga cada comando, texto e botão à sua função.

    Está separada do main() porque o bot tem dois modos de arrancar (no PC, com o main(),
    e no alojamento, com o servidor_web.py) e os dois precisam exatamente da mesma lista.
    """
    # Só mensagens novas: se editares uma mensagem, o bot não a regista outra vez
    novas = filters.UpdateType.MESSAGE

    # Cada comando (o que escreves a seguir à barra, como /semana) ligado à função que lhe
    # responde.
    comandos = {
        "id": handlers.meu_id,
        "start": handlers.start,
        "ajuda": handlers.ajuda,
        "desfazer": handlers.desfazer,
        "corrigir": handlers.corrigir,
        "orcamento": handlers.orcamento,
        "avisar": handlers.avisar,
        "hoje": handlers.hoje,
        "semana": handlers.semana,
        "mes": handlers.mes,
        "comparar": handlers.comparar,
        "lista": handlers.lista,
        "temas": handlers.temas,
        "exportar": handlers.exportar,
        "limpar": handlers.limpar,
    }
    for nome, funcao in comandos.items():
        app.add_handler(CommandHandler(nome, funcao, filters=novas))

    # Texto normal (as despesas): tudo o que não é um comando
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & novas, handlers.texto))

    # Botões. O 'pattern' escolhe a função pelo início da etiqueta do botão
    botoes = [
        (handlers.escolheu_categoria, r"^c:"),
        (handlers.escolheu_subcategoria, r"^s:"),
        (handlers.pediu_nova_categoria, r"^nc:"),
        (handlers.pediu_nova_subcategoria, r"^ns:"),
        (handlers.escolheu_lista, r"^l:"),
        (handlers.escolheu_comparar, r"^cmp:"),
        (handlers.confirmou_limpar, r"^limpar:"),
    ]
    for funcao, padrao in botoes:
        app.add_handler(CallbackQueryHandler(funcao, pattern=padrao))

    app.add_error_handler(handlers.erro)


def main():
    """Modo PC: monta o bot e fica a perguntar ao Telegram se há mensagens novas."""
    # Cria o bot com o token (a 'palavra-passe' dele, lida do .env). O post_init manda o menu
    # de comandos ao Telegram quando o bot arranca.
    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).post_init(depois_de_iniciar).build()

    # A ligação à base de dados abre uma vez e fica guardada, para todas as funções a usarem
    ligacao = db.ligar()
    db.criar_tabelas(ligacao)
    db.semear(ligacao)
    app.bot_data["ligacao"] = ligacao

    registar_handlers(app)
    # Fica a perguntar ao Telegram, sem parar, se há mensagens novas. Só termina quando
    # carregas em Ctrl+C.
    app.run_polling()


if __name__ == "__main__":
    main()
