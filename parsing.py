"""Ler e limpar o texto que escreves ao bot. Não mexe na base de dados nem no Telegram."""

import unicodedata
from decimal import Decimal, InvalidOperation

# Palavras sem significado: o bot ignora-as ao aprender, para "uma pizza" ensinar "pizza"
PALAVRAS_A_IGNORAR = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "com", "e", "para", "pra",
    "no", "na", "nos", "nas", "em", "ao", "aos", "por", "pelo", "pela",
}

# Palavras que mudam a data de uma despesa, e quantos dias atrás significam
DIAS_ATRAS = {"hoje": 0, "ontem": 1, "anteontem": 2}

# Valor máximo aceite numa despesa (em euros). Protege contra enganos a escrever.
VALOR_MAXIMO = Decimal("1000000")


def normalizar(texto):
    """Põe em minúsculas, tira acentos e pontuação: 'Café,' vira 'cafe'.

    Serve para o bot reconhecer a mesma palavra escrita de formas diferentes.
    """
    # NFD separa cada letra do seu acento ('é' passa a 'e' + um acento solto)
    decomposto = unicodedata.normalize("NFD", texto.lower())
    # Deita fora os acentos soltos (a categoria 'Mn' do Unicode)
    sem_acentos = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    # Tudo o que não for letra ou número vira espaço; depois arrumamos os espaços
    limpo = "".join(c if c.isalnum() else " " for c in sem_acentos)
    return " ".join(limpo.split())


def palavras_da_descricao(descricao):
    """Lista de palavras limpas e com significado: 'Uma pizza' dá ['pizza']."""
    return [
        palavra
        for palavra in normalizar(descricao).split()
        if palavra not in PALAVRAS_A_IGNORAR and not palavra.isdigit()
    ]


def parse_valor(texto):
    """Converte '3,5' ou '3.5' em cêntimos (350). Devolve None se não for um valor válido."""
    try:
        # O Decimal faz contas exatas com decimais. O float erra: 0.1 + 0.2 dá 0.30000000000000004
        valor = Decimal(texto.strip().replace("€", "").replace(",", "."))
    except InvalidOperation:
        return None
    # O Decimal aceita "nan" e "inf", que não são dinheiro. Isto tem de vir ANTES
    # de comparar com 0, porque comparar um nan dá erro.
    if not valor.is_finite() or valor <= 0 or valor > VALOR_MAXIMO:
        return None
    return int(valor * 100)


def parse_despesa(texto):
    """Lê '3,5 café' e devolve (350, 'café'), ou None se não for uma despesa."""
    # Divide o texto em duas partes: o preço e o resto
    partes = texto.strip().split(maxsplit=1)

    # 1. se não houver 2 partes, devolve None
    if len(partes) < 2:
        return None

    # Forma direta e sem erros: separa o número da descrição
    valor_texto, descricao_suja = partes
    descricao = descricao_suja.strip()

    # 2. valor_texto = a primeira parte, com a vírgula trocada por ponto
    valor_texto = valor_texto.replace(",", ".")

    # 3. tenta converter para Decimal; se falhar, devolve None
    try:
        valor = Decimal(valor_texto)
    except InvalidOperation:
        return None

    # 4. se o valor for zero ou negativo, devolve None
    # ACRESCENTADO: o Decimal aceita "nan" (não é um número) e "inf" (infinito), que não
    # são dinheiro e fariam o programa rebentar. O is_finite() tem de vir ANTES de
    # comparar com 0, porque comparar um nan com 0 dá erro.
    if not valor.is_finite() or valor <= 0:
        return None

    # 5. cêntimos = int(valor * 100)
    centimos = int(valor * 100)

    # 6. devolve (cêntimos, descrição)
    return (centimos, descricao)


def separar_dia(texto):
    """Tira 'ontem', 'anteontem' ou 'hoje' do início: 'ontem 12 jantar' dá (1, '12 jantar')."""
    partes = texto.strip().split(maxsplit=1)
    if partes and normalizar(partes[0]) in DIAS_ATRAS:
        resto = partes[1] if len(partes) > 1 else ""
        return DIAS_ATRAS[normalizar(partes[0])], resto
    return 0, texto


def parse_mensagem(texto):
    """Junta tudo: devolve (cêntimos, descrição, dias_atrás) ou None se não for uma despesa."""
    dias, resto = separar_dia(texto)
    resultado = parse_despesa(resto)
    if resultado is None:
        return None
    centimos, descricao = resultado
    # Limita o tamanho da descrição, para nunca dar problemas nas respostas
    return centimos, descricao[:100], dias
