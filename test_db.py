from datetime import date, timedelta

import db
import tempo

# --- datas (já escritas)
assert tempo.segunda_da_semana(date(2026, 11, 8)) == date(2026, 11, 2)  # domingo -> segunda
assert tempo.segunda_da_semana(date(2026, 11, 2)) == date(2026, 11, 2)  # segunda -> ela própria
assert tempo.primeiro_do_mes_seguinte(date(2026, 12, 15)) == date(2027, 1, 1)
assert tempo.primeiro_do_mes_seguinte(date(2026, 1, 31)) == date(2026, 2, 1)
assert tempo.primeiro_do_mes_anterior(date(2026, 1, 15)) == date(2025, 12, 1)
print("datas: certo")

ligacao = db.ligar(":memory:")  # base de dados temporária, só na memória
db.criar_tabelas(ligacao)
db.semear(ligacao)


def destino(descricao):
    # Ajuda dos testes: devolve o nome ('Refeições › Jantar') em vez de números, para ler melhor
    resultado = db.encontrar_destino(ligacao, descricao)
    if resultado is None:
        return None
    return db.nome_destino(ligacao, *resultado)


# --- 1. encontrar_destino (a TUA função)
assert destino("café") == "Refeições › Pequeno-almoço"
assert destino("Café, com leite") == "Refeições › Pequeno-almoço"  # maiúsculas e vírgula
assert destino("cafe") == "Refeições › Pequeno-almoço"  # sem acento
assert destino("uma pizza") == "Refeições › Jantar"
assert destino("autocarro") == "Transportes"
assert destino("continente") == "Supermercado"
assert destino("gelado") is None  # palavra desconhecida: o bot pergunta
print("encontrar_destino: certo")

# --- 2. categorias novas
refeicoes = db.encontrar_categoria(ligacao, "refeicoes")
assert refeicoes is not None
assert db.encontrar_categoria(ligacao, "refe") is None  # exato por defeito
assert db.encontrar_categoria(ligacao, "refe", aproximado=True) == refeicoes
nova = db.criar_categoria(ligacao, "Animais")
assert db.criar_categoria(ligacao, "animais") == nova  # não duplica
sub = db.criar_subcategoria(ligacao, nova, "Ração")
assert db.criar_subcategoria(ligacao, nova, "racao") == sub
print("categorias: certo")

# --- 3. guardar, classificar e desfazer
assert db.apagar_ultima(ligacao) is None  # ainda não há despesas
id1 = db.guardar_despesa(ligacao, 350, "café", refeicoes, None)
id2 = db.guardar_despesa(ligacao, 1000, "gelado")
assert db.id_ultima_despesa(ligacao) == id2
db.classificar_despesa(ligacao, id2, refeicoes, None)
assert db.obter_despesa(ligacao, id2)[:2] == (1000, "gelado")
print("guardar: certo")

# --- 4. períodos (esta semana, e uma despesa de há 8 dias que fica de fora)
db.guardar_despesa(ligacao, 5000, "velho", None, None, quando=tempo.agora() - timedelta(days=8))
segunda = tempo.segunda_da_semana()
fim = segunda + timedelta(days=7)
total, por_categoria = db.resumo_periodo(ligacao, segunda, fim)
assert total == 1350
assert por_categoria == [("Refeições", 1350)]
movimentos = db.listar_movimentos(ligacao, refeicoes, segunda, fim)
assert [(d, c) for _, d, c in movimentos] == [("café", 350), ("gelado", 1000)]
assert db.listar_movimentos(ligacao, None, segunda, fim) == []  # nada sem categoria
print("períodos: certo")

# --- 5. orçamento e aviso
assert db.verificar_aviso(ligacao) is None  # sem orçamento definido
db.definir_orcamento(ligacao, 2000)  # 20 €, aviso aos 80% (16 €)
assert db.verificar_aviso(ligacao) is None  # 13,50 € ainda não chega
db.guardar_despesa(ligacao, 300, "extra", refeicoes, None)  # 16,50 €
assert db.verificar_aviso(ligacao) == (1650, 2000, 80)
assert db.verificar_aviso(ligacao) is None  # só avisa uma vez por semana
assert db.apagar_ultima(ligacao) == (300, "extra")  # volta abaixo do limite: rearma o aviso
db.guardar_despesa(ligacao, 300, "extra", refeicoes, None)
assert db.verificar_aviso(ligacao) == (1650, 2000, 80)  # avisa outra vez
db.definir_orcamento(ligacao, 1000)  # baixar o orçamento: já passaste o novo limite
assert db.verificar_aviso(ligacao) == (1650, 1000, 80)  # avisa logo, uma vez
print("orçamento e aviso: certo")

# --- 5b. gastos agrupados por categoria (com uma despesa sem categoria, a maior da semana)
db.guardar_despesa(ligacao, 2000, "xpto")
grupos = db.despesas_por_categoria(ligacao, segunda, fim)
assert [(nome, total) for nome, total, _ in grupos] == [("Sem categoria", 2000), ("Refeições", 1650)]
assert [descricao for _, descricao, _ in grupos[0][2]] == ["xpto"]
assert [descricao for _, descricao, _ in grupos[1][2]] == ["café", "gelado", "extra"]
assert db.despesas_por_categoria(ligacao, fim, fim + timedelta(days=7)) == []  # semana seguinte: nada
assert db.apagar_ultima(ligacao) == (2000, "xpto")  # tira a despesa de teste
print("detalhe por categoria: certo")

# --- 6. temas, exportar e limpar
nomes = dict(db.temas(ligacao))
assert "autocarro" in nomes["Transportes"][0][1]
assert nomes["Outros"] == []
assert len(db.todas_as_despesas(ligacao)) == 4
assert db.limpar_despesas(ligacao) == 4
assert db.todas_as_despesas(ligacao) == []
assert db.id_ultima_despesa(ligacao) is None
print("temas, exportar e limpar: certo")

print("Tudo certo!")
