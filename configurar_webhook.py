"""Liga ou desliga o webhook do Telegram.

Corre-se UMA vez, depois de o servidor_web.py estar posto no alojamento:

    python configurar_webhook.py          diz ao Telegram para enviar as mensagens ao alojamento
    python configurar_webhook.py apagar   desliga isso (para voltares a usar o bot.py no PC)
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# O .env fica ao lado deste ficheiro
PASTA = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PASTA, ".env"))

# Mesmo truque do servidor_web.py: nas contas gratuitas da PythonAnywhere passa-se por um proxy
proxy = os.getenv("PROXY_URL")
if proxy:
    os.environ.setdefault("HTTPS_PROXY", proxy)

from telegram import Bot  # noqa: E402  (tem de vir depois das linhas de cima)

import bot  # noqa: E402  (só para ir buscar a lista de comandos)


async def ligar_webhook():
    """Diz ao Telegram o endereço para onde deve enviar as mensagens."""
    async with Bot(os.environ["BOT_TOKEN"]) as telegram_bot:
        await telegram_bot.set_webhook(
            url=os.environ["WEBHOOK_URL"],
            secret_token=os.environ["WEBHOOK_SECRET"],  # o servidor_web.py confere este segredo
            allowed_updates=["message", "callback_query"],  # só mensagens e botões
            max_connections=1,  # uma mensagem de cada vez
            drop_pending_updates=True,  # ignora mensagens que tenham ficado à espera
        )
        await telegram_bot.set_my_commands(bot.COMANDOS)  # o menu que aparece ao escrever "/"

        # Pergunta ao Telegram como ficou, para confirmares que correu bem
        info = await telegram_bot.get_webhook_info()
        print("Webhook ligado em:", info.url)
        if info.last_error_message:
            print("Último erro registado pelo Telegram:", info.last_error_message)


async def apagar_webhook():
    """Desliga o webhook. Depois disto o bot.py volta a poder correr no PC."""
    async with Bot(os.environ["BOT_TOKEN"]) as telegram_bot:
        await telegram_bot.delete_webhook()
        print("Webhook desligado.")


if __name__ == "__main__":
    # sys.argv são as palavras escritas a seguir ao nome do ficheiro
    if len(sys.argv) > 1 and sys.argv[1] == "apagar":
        asyncio.run(apagar_webhook())
    else:
        asyncio.run(ligar_webhook())
