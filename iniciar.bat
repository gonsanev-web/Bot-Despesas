@echo off
rem Liga o bot com dois cliques.
rem O cd garante que corre a partir desta pasta, onde estao o .env e a base de dados.
cd /d "%~dp0"
rem Usa o Python do ambiente .venv, por isso nao precisas de o ativar.
".venv\Scripts\python.exe" bot.py
rem O pause deixa a janela aberta se o bot parar, para leres a mensagem de erro.
pause
