"""Testes da leitura do texto (parsing.py): valores, descrições e dias.

Corre-se com: python test_parsing.py. Se alguma linha falhar, o Python mostra qual.
"""

from parsing import (
    normalizar,
    palavras_da_descricao,
    parse_despesa,
    parse_mensagem,
    parse_valor,
    separar_dia,
)

# --- parse_valor (já escrita): só o valor
assert parse_valor("3,5") == 350
assert parse_valor("3.5") == 350
assert parse_valor("12") == 1200
assert parse_valor("0,99") == 99
assert parse_valor("3,5€") == 350
assert parse_valor("0") is None
assert parse_valor("-5") is None
assert parse_valor("nan") is None  # "nan" significa "não é um número"
assert parse_valor("inf") is None  # infinito
assert parse_valor("abc") is None
assert parse_valor("") is None
assert parse_valor("9999999") is None  # acima do valor máximo
print("parse_valor: certo")

# --- parse_despesa (a TUA função): valor e descrição
assert parse_despesa("3,5 café") == (350, "café")
assert parse_despesa("3.5 café") == (350, "café")
assert parse_despesa("12 jantar com amigos") == (1200, "jantar com amigos")
assert parse_despesa("0,99 pastilha") == (99, "pastilha")
assert parse_despesa("  3,5   café  ") == (350, "café")
assert parse_despesa("café") is None
assert parse_despesa("3,5") is None  # sem descrição
assert parse_despesa("-5 café") is None  # valor negativo
assert parse_despesa("0 café") is None  # valor zero
assert parse_despesa("nan café") is None
assert parse_despesa("inf café") is None
print("parse_despesa: certo")

# --- normalizar e palavras_da_descricao (já escritas)
assert normalizar("Café,") == "cafe"
assert normalizar("  Pão   de  Ló! ") == "pao de lo"
assert palavras_da_descricao("Uma pizza") == ["pizza"]
assert palavras_da_descricao("café com leite") == ["cafe", "leite"]
assert palavras_da_descricao("uma de") == []
assert palavras_da_descricao("2 bolos") == ["bolos"]
print("normalizar: certo")

# --- separar_dia e parse_mensagem (já escritas, usam a tua parse_despesa)
assert separar_dia("ontem 12 jantar") == (1, "12 jantar")
assert separar_dia("Anteontem 3 café") == (2, "3 café")
assert separar_dia("3,5 café") == (0, "3,5 café")
assert separar_dia("ontem") == (1, "")
assert parse_mensagem("3,5 café") == (350, "café", 0)
assert parse_mensagem("ontem 12 jantar com amigos") == (1200, "jantar com amigos", 1)
assert parse_mensagem("ontem") is None
assert parse_mensagem("olá") is None
print("parse_mensagem: certo")

print("Tudo certo!")
