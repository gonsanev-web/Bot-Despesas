"""Testes do /comparar e do tratamento de erros. Não precisam de ligação à internet."""

import asyncio
import logging
import types
from datetime import datetime, time, timedelta

from telegram.error import BadRequest

import db
import handlers
import tempo

# --- 1. euros_com_sinal: o sinal vai à frente do valor
assert handlers.euros_com_sinal(1200) == "+12,00 €"
assert handlers.euros_com_sinal(-800) == "-8,00 €"
assert handlers.euros_com_sinal(0) == "0,00 €"
print("euros_com_sinal: certo")

# --- 2. formatar_comparacao com números inventados
# Formato dos dados: (total, [(categoria, cêntimos), ...]), como devolve db.resumo_periodo
atual = (4720, [("Refeições", 4200), ("Transportes", 520)])
anterior = (4500, [("Refeições", 3000), ("Lazer", 1500)])
texto = handlers.formatar_comparacao(
    "Esta semana", "Semana passada", "16/11 a 22/11", "09/11 a 15/11", atual, anterior
)
assert "16/11 a 22/11 (em curso) contra 09/11 a 15/11" in texto
assert "Esta semana: 47,20 €" in texto
assert "Semana passada: 45,00 €" in texto
assert "Diferença: +2,20 € (+5%)" in texto  # 220 / 4500 = 4,9%, arredondado para 5
assert "Refeições: +12,00 € (30,00 € → 42,00 €)" in texto
assert "Lazer: -15,00 € (15,00 € → 0,00 €)" in texto  # categoria que desapareceu
assert "Transportes: +5,20 € (0,00 € → 5,20 €)" in texto  # categoria nova
# A ordem é a da maior mudança para a menor: Lazer (15,00), Refeições (12,00), Transportes (5,20)
assert texto.index("Lazer:") < texto.index("Refeições: +") < texto.index("Transportes:")

# Totais iguais: a diferença é zero e não há lista de mudanças
igual = (1000, [("Lazer", 1000)])
texto = handlers.formatar_comparacao("Esta semana", "Semana passada", "a", "b", igual, igual)
assert "Diferença: 0,00 € (0%)" in texto
assert "O que mais mudou" not in texto

# Sem despesas no período anterior: não dá para comparar
texto = handlers.formatar_comparacao(
    "Esta semana", "Semana passada", "a", "b", (1000, [("Lazer", 1000)]), (0, [])
)
assert "Semana passada: sem despesas registadas." in texto
assert "Diferença" not in texto

# Sem despesas em nenhum dos dois
texto = handlers.formatar_comparacao("Esta semana", "Semana passada", "a", "b", (0, []), (0, []))
assert "Ainda sem despesas nestes dois períodos." in texto

# Gastaste tudo na semana passada e nada nesta: -100%
texto = handlers.formatar_comparacao(
    "Esta semana", "Semana passada", "a", "b", (0, []), (1000, [("Lazer", 1000)])
)
assert "Diferença: -10,00 € (-100%)" in texto
print("formatar_comparacao: certo")

# --- 3. texto_comparar com despesas em datas reais de calendário
ligacao = db.ligar(":memory:")  # base de dados temporária, só na memória
db.criar_tabelas(ligacao)
db.semear(ligacao)
refeicoes = db.encontrar_categoria(ligacao, "refeicoes")
lazer = db.encontrar_categoria(ligacao, "lazer")


def ao_meio_dia(dia):
    """Um datetime às 12:00 desse dia, para guardar despesas em datas escolhidas."""
    return datetime.combine(dia, time(12, 0))


# Semana: o domingo antes de segunda ainda é a semana passada, e a segunda já é a atual
segunda = tempo.segunda_da_semana()
db.guardar_despesa(ligacao, 3000, "a", refeicoes, None, quando=ao_meio_dia(segunda - timedelta(days=7)))
db.guardar_despesa(ligacao, 1500, "b", lazer, None, quando=ao_meio_dia(segunda - timedelta(days=1)))
db.guardar_despesa(ligacao, 4200, "c", refeicoes, None, quando=ao_meio_dia(segunda))
texto = handlers.texto_comparar(ligacao, "semana")
domingo = segunda + timedelta(days=6)
anterior_segunda = segunda - timedelta(days=7)
assert f"{segunda:%d/%m} a {domingo:%d/%m} (em curso)" in texto
assert f"contra {anterior_segunda:%d/%m} a {segunda - timedelta(days=1):%d/%m}" in texto
assert "Esta semana: 42,00 €" in texto
assert "Semana passada: 45,00 €" in texto
assert "Diferença: -3,00 € (-7%)" in texto  # -300 / 4500 = -6,7%
print("semana: certo")

# Mês: base de dados nova, para as datas da semana não se misturarem com as do mês
ligacao = db.ligar(":memory:")
db.criar_tabelas(ligacao)
db.semear(ligacao)
lazer = db.encontrar_categoria(ligacao, "lazer")
primeiro = tempo.primeiro_do_mes()
ultimo_do_mes_passado = primeiro - timedelta(days=1)
primeiro_do_mes_passado = tempo.primeiro_do_mes_anterior()
db.guardar_despesa(ligacao, 1000, "d", lazer, None, quando=ao_meio_dia(primeiro))  # dia 1 deste mês
db.guardar_despesa(ligacao, 500, "e", lazer, None, quando=ao_meio_dia(ultimo_do_mes_passado))
db.guardar_despesa(ligacao, 700, "f", lazer, None, quando=ao_meio_dia(primeiro_do_mes_passado))
texto = handlers.texto_comparar(ligacao, "mes")
ultimo_deste_mes = tempo.primeiro_do_mes_seguinte() - timedelta(days=1)
assert f"{primeiro:%d/%m} a {ultimo_deste_mes:%d/%m} (em curso)" in texto
assert f"contra {primeiro_do_mes_passado:%d/%m} a {ultimo_do_mes_passado:%d/%m}" in texto
assert "Este mês: 10,00 €" in texto
assert "Mês passado: 12,00 €" in texto  # as despesas do dia 1 e do último dia contam as duas
assert "Diferença: -2,00 € (-17%)" in texto  # -200 / 1200 = -16,7%
print("mês: certo")

# --- 4. erro(): tocar duas vezes no mesmo botão não é um erro a sério
registos = []  # aqui guardamos o que o erro() tentar escrever no registo
logging_original = logging.error
logging.error = lambda *args, **kwargs: registos.append(args)  # troca o logging.error por um apanhador

# Com update=None o erro() só regista (não tenta responder), por isso não precisamos de um Update
asyncio.run(handlers.erro(None, types.SimpleNamespace(error=BadRequest("Message is not modified: igual"))))
assert registos == []  # este erro é ignorado em silêncio

asyncio.run(handlers.erro(None, types.SimpleNamespace(error=BadRequest("Chat not found"))))
assert len(registos) == 1  # os outros erros continuam a ser registados

logging.error = logging_original  # repõe o logging.error verdadeiro
print("erro(): certo")

print("Tudo certo!")
