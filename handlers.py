"""O que o bot faz em resposta a cada mensagem, comando e botão."""

import csv
import functools
import io
import logging
import os
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import db
import tempo
from parsing import normalizar, palavras_da_descricao, parse_mensagem, parse_valor

# Nomes dos meses, para o /mes escrever 'Mês de novembro'. Janeiro é a posição 0 da lista.
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

# O Telegram recusa mensagens com mais de 4096 caracteres. Cortamos antes disso.
LIMITE_MENSAGEM = 3500

# O texto que o /start e o /ajuda mostram. Se criares um comando novo, lembra-te de o acrescentar
# aqui.
TEXTO_AJUDA = (
    "Escreve uma despesa: 3,5 café  (ou: ontem 12 jantar)\n\n"
    "/desfazer  apaga o último registo\n"
    "/corrigir  muda a categoria do último registo\n"
    "/hoje  gastos de hoje\n"
    "/semana, /mes  cada gasto, por categoria\n"
    "/comparar  compara a semana ou o mês com o anterior\n"
    "/lista  movimentos de uma categoria (esta semana)\n"
    "/orcamento 600  orçamento mensal\n"
    "/avisar 80  aviso quando chegares aos 80%\n"
    "/temas  categorias e palavras que o bot conhece\n"
    "/exportar  ficheiro CSV com tudo\n"
    "/limpar  apaga todas as despesas"
)


# ------------------------------------------------------------------ utilitários


def autorizado(update: Update) -> bool:
    """True só se a mensagem vier de ti (o teu número está no .env, em MEU_ID)."""
    # Quem escreveu a mensagem. Pode não existir em alguns tipos de mensagens, por isso se
    # testa a seguir.
    utilizador = update.effective_user
    # O teu número de utilizador vem do ficheiro .env. Se faltar, fica 0 e ninguém é
    # autorizado.
    meu_id = int(os.getenv("MEU_ID", "0"))
    return utilizador is not None and utilizador.id == meu_id


def so_dono(funcao):
    """Decorador: embrulha uma função para ela só correr se a mensagem for tua.

    Para outras pessoas o bot fica calado. Em vez de repetir o 'if' em todas as
    funções, escreve-se @so_dono por cima delas.
    """

    @functools.wraps(funcao)  # a função embrulhada mantém o nome e a explicação da original
    async def embrulho(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """A função que realmente corre: vê quem escreveu e só depois chama a original."""
        if not autorizado(update):
            return  # não és tu: o bot não responde nada
        await funcao(update, context)

    return embrulho


def ligacao_de(context):
    """A ligação à base de dados, guardada quando o bot arrancou."""
    return context.application.bot_data["ligacao"]


def euros(centimos):
    """350 vira '3,50 €'. divmod dá o quociente e o resto da divisão."""
    inteiros, cents = divmod(centimos, 100)
    return f"{inteiros},{cents:02d} €"


def teclado(botoes):
    """Faz o teclado de botões. 'botoes' é uma lista de (texto, callback_data), 2 por linha.

    O callback_data é uma etiqueta que o Telegram nos devolve quando carregas no botão.
    """
    # range(0, n, 2) conta de 2 em 2, e botoes[i : i + 2] corta esses 2 botões: é uma linha do teclado
    linhas = [
        [InlineKeyboardButton(texto, callback_data=dados) for texto, dados in botoes[i : i + 2]]
        for i in range(0, len(botoes), 2)
    ]
    return InlineKeyboardMarkup(linhas)


async def enviar_longo(mensagem, texto):
    """Envia um texto grande em vários pedaços, cortando sempre entre linhas."""
    # Vai juntando linhas num pedaço. Quando mais uma linha faria o pedaço passar o limite do
    # Telegram, envia o que já tem e começa outro. Assim corta-se sempre entre linhas, nunca a
    # meio.
    pedaco = ""
    for linha in texto.split("\n"):
        if len(pedaco) + len(linha) + 1 > LIMITE_MENSAGEM:
            await mensagem.reply_text(pedaco)
            pedaco = ""
        pedaco += linha + "\n"
    # No fim, envia o que sobrou (se não estiver vazio).
    if pedaco.strip():
        await mensagem.reply_text(pedaco)


def rotulo_dia(criada_em):
    """' — ontem', ' — anteontem' ou ' — 05/11' se a despesa não for de hoje."""
    # criada_em é do género '2026-11-08 20:15:00': as 10 primeiras letras são a data. Depois
    # conta-se quantos dias passaram desde então.
    dia = date.fromisoformat(criada_em[:10])
    dias = (tempo.hoje() - dia).days
    # 0 dias quer dizer hoje, e nesse caso não se escreve nada ao lado do registo.
    if dias == 0:
        return ""
    if dias == 1:
        return " — ontem"
    if dias == 2:
        return " — anteontem"
    return f" — {dia:%d/%m}"


def resumo(ligacao, despesa_id):
    """A primeira linha de quase todas as respostas: 'Registado: 3,50 € (café)'."""
    # Vai à base de dados buscar a despesa pelo número dela e monta a frase com o valor, a
    # descrição e (se não for de hoje) o dia.
    centimos, descricao, criada_em = db.obter_despesa(ligacao, despesa_id)
    return f"Registado: {euros(centimos)} ({descricao}){rotulo_dia(criada_em)}"


def botoes_categorias(ligacao, despesa_id):
    """Botões das categorias, mais '➕ Nova' e 'Sem categoria'.

    Etiquetas: c:<despesa>:<categoria> (0 = sem categoria) e nc:<despesa> (nova).
    """
    # Um botão por categoria. O texto do botão é o nome. A etiqueta escondida
    # (c:despesa:categoria) é o que o Telegram nos devolve quando tocas, para sabermos que
    # despesa e que categoria escolheste.
    botoes = [
        (nome, f"c:{despesa_id}:{categoria_id}")
        for categoria_id, nome in db.listar_categorias(ligacao)
    ]
    # Dois botões fixos no fim: criar uma categoria nova, ou deixar a despesa sem categoria (o
    # 0 quer dizer 'nenhuma').
    botoes.append(("➕ Nova", f"nc:{despesa_id}"))
    botoes.append(("Sem categoria", f"c:{despesa_id}:0"))
    return botoes


def concluir(ligacao, despesa_id, categoria_id, subcategoria_id):
    """Guarda a classificação, ensina a palavra ao bot e devolve o texto final."""
    # Passo 1: grava na despesa a categoria (e subcategoria) que escolheste.
    db.classificar_despesa(ligacao, despesa_id, categoria_id, subcategoria_id)
    # Passo 2: ensina o bot. A palavra principal desta despesa passa a apontar para esta
    # categoria, e da próxima vez ele já sabe sem perguntar. Se escolheste 'Sem categoria',
    # não há nada a aprender.
    if categoria_id is not None:
        descricao = db.obter_despesa(ligacao, despesa_id)[1]
        palavras = palavras_da_descricao(descricao)
        if palavras:
            # O bot aprende a primeira palavra com significado ("uma pizza" ensina "pizza")
            db.aprender_palavra(ligacao, palavras[0], categoria_id, subcategoria_id)
    # Passo 3: monta a resposta final, com a frase do registo e, por baixo, 'Categoria ›
    # Subcategoria'.
    destino = db.nome_destino(ligacao, categoria_id, subcategoria_id)
    return f"{resumo(ligacao, despesa_id)}\n{destino}"


def texto_aviso(gasto, orcamento):
    """A mensagem do aviso de orçamento."""
    if gasto >= orcamento:
        return f"Atenção: passaste o orçamento do mês ({euros(gasto)} de {euros(orcamento)})."
    # Que parte do orçamento já gastaste, em percentagem inteira (o // é a divisão sem
    # decimais).
    percentagem = gasto * 100 // orcamento
    falta = orcamento - gasto
    return (
        f"Atenção: chegaste aos {percentagem}% do orçamento "
        f"({euros(gasto)} de {euros(orcamento)}). Faltam {euros(falta)} até ao fim do mês."
    )


async def avisar_se_preciso(mensagem, ligacao):
    """Manda o aviso do orçamento, se for a altura. Vai numa mensagem à parte,
    para não desaparecer quando os botões da categoria são substituídos."""
    # verificar_aviso devolve None se não for altura de avisar (sem orçamento, abaixo do
    # limite, ou já avisado este mês).
    aviso = db.verificar_aviso(ligacao)
    if aviso:
        # O '_' ignora a percentagem, que aqui não faz falta.
        gasto, orcamento, _ = aviso
        await mensagem.reply_text(texto_aviso(gasto, orcamento))


async def despesa_existe(query, ligacao, despesa_id):
    """Se apagaste a despesa com /desfazer, os botões antigos deixam de servir."""
    # Os botões antigos podem apontar para uma despesa que entretanto apagaste com /desfazer.
    # Em vez de dar erro, avisa.
    if db.obter_despesa(ligacao, despesa_id) is None:
        await query.edit_message_text("Esse registo já foi apagado.")
        return False
    return True


def formatar_resumo(titulo, total, por_categoria, orcamento=None):
    """Texto de um resumo (hoje, semana ou mês)."""
    if total == 0:
        return f"{titulo}\nAinda sem despesas."
    linha_total = f"Total: {euros(total)}"
    if orcamento:
        # O "//" é a divisão inteira, sem decimais: 107,5% aparece como 107%
        linha_total += f" de {euros(orcamento)} ({total * 100 // orcamento}%)"
    # Cabeçalho (título e total) e uma linha em branco. A seguir vem uma linha por categoria,
    # no formato 'Nome: valor'.
    linhas = [titulo, linha_total, ""]
    linhas += [f"{nome}: {euros(centimos)}" for nome, centimos in por_categoria]
    return "\n".join(linhas)


def formatar_detalhado(titulo, grupos, orcamento=None):
    """Texto de um resumo com cada gasto, agrupado por categoria (usado no /semana e /mes).

    'grupos' vem de db.despesas_por_categoria: lista de (categoria, total, movimentos).
    """
    # O total geral é a soma dos totais de cada categoria
    total = sum(subtotal for _, subtotal, _ in grupos)
    if total == 0:
        return f"{titulo}\nAinda sem despesas."

    linha_total = f"Total: {euros(total)}"
    if orcamento:
        # O "//" é a divisão inteira, sem decimais: 107,5% aparece como 107%
        linha_total += f" de {euros(orcamento)} ({total * 100 // orcamento}%)"

    linhas = [titulo, linha_total]
    for nome, subtotal, movimentos in grupos:
        linhas.append("")  # linha em branco a separar cada categoria
        linhas.append(f"{nome}: {euros(subtotal)}")
        for criada_em, descricao, centimos in movimentos:
            # criada_em é '2026-11-08 20:15:00': as 10 primeiras letras são a data
            dia = date.fromisoformat(criada_em[:10])
            linhas.append(f"  {dia:%d/%m}  {descricao}  {euros(centimos)}")
    return "\n".join(linhas)


# ---------------------------------------------------------------- comandos simples


async def meu_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde a toda a gente (sem @so_dono), para descobrires o teu número de utilizador."""
    await update.effective_message.reply_text(f"O teu ID é {update.effective_user.id}")


@so_dono
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start: o Telegram manda isto quando abres o bot pela primeira vez. Mostra a ajuda."""
    await update.effective_message.reply_text(TEXTO_AJUDA)


@so_dono
async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ajuda: a lista de comandos."""
    await update.effective_message.reply_text(TEXTO_AJUDA)


# --------------------------------------------------------------- registar despesas


@so_dono
async def texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qualquer mensagem de texto que não seja um comando: normalmente uma despesa."""
    mensagem = update.effective_message
    ligacao = ligacao_de(context)

    # Se estavas a dar nome a uma categoria nova, esta mensagem é o nome...
    pendente = context.user_data.get("pendente")
    if pendente and mensagem.text.strip()[:1].isdigit():
        # ...a não ser que comece por um número: aí é uma despesa nova, e cancelamos o resto
        context.user_data.pop("pendente", None)
        pendente = None
    if pendente:
        await tratar_nome_novo(mensagem, context, pendente)
        return

    # Tenta ler 'valor + descrição' (e o 'ontem' ou 'anteontem', se vier). Se não der, a
    # mensagem não é uma despesa.
    resultado = parse_mensagem(mensagem.text)
    if resultado is None:
        await mensagem.reply_text("Não percebi. Escreve assim: 3,5 café  (ou: ontem 12 jantar)")
        return

    centimos, descricao, dias = resultado
    # Se escreveste 'ontem', a despesa fica com a data de há 1 dia (dias vale 0 quando não
    # disseste nada).
    quando = tempo.agora() - timedelta(days=dias)
    # Vê se o bot já conhece alguma palavra da descrição. A categoria vem da tabela das
    # palavras aprendidas.
    destino = db.encontrar_destino(ligacao, descricao)

    if destino is None:
        # Palavra desconhecida: guarda já, sem categoria, e pergunta qual é
        despesa_id = db.guardar_despesa(ligacao, centimos, descricao, quando=quando)
        await mensagem.reply_text(
            f"{resumo(ligacao, despesa_id)}\nEm que categoria entra?",
            reply_markup=teclado(botoes_categorias(ligacao, despesa_id)),
        )
    else:
        categoria_id, subcategoria_id = destino
        despesa_id = db.guardar_despesa(
            ligacao, centimos, descricao, categoria_id, subcategoria_id, quando=quando
        )
        nome = db.nome_destino(ligacao, categoria_id, subcategoria_id)
        await mensagem.reply_text(f"{resumo(ligacao, despesa_id)}\n{nome}")

    # Depois de registar, vê se o mês já chegou à percentagem do orçamento e, se sim, avisa
    # numa mensagem à parte.
    await avisar_se_preciso(mensagem, ligacao)


async def tratar_nome_novo(mensagem, context, pendente):
    """Recebe o nome de uma categoria ou subcategoria nova (depois de tocares em '➕ Nova')."""
    ligacao = ligacao_de(context)
    # O texto que escreveste é o nome da categoria ou subcategoria nova.
    nome = mensagem.text.strip()

    # Escrever 'cancelar' desiste: a despesa fica sem categoria e podes classificá-la depois
    # com /corrigir.
    if normalizar(nome) == "cancelar":
        context.user_data.pop("pendente", None)
        await mensagem.reply_text(
            "Cancelado. A despesa ficou sem categoria (usa /corrigir para a classificar)."
        )
        return
    # Nomes vazios ou enormes não servem (os botões ficavam feios), por isso pede-se outro.
    if not 1 <= len(nome) <= 30:
        await mensagem.reply_text("O nome tem de ter entre 1 e 30 letras. Escreve outra vez, ou 'cancelar'.")
        return

    # O 'pendente' lembra qual era a despesa à espera de categoria e se o nome é de uma
    # categoria ou de uma subcategoria.
    despesa_id = pendente["despesa_id"]
    # Se entretanto apagaste a despesa com /desfazer, já não há nada a classificar.
    if db.obter_despesa(ligacao, despesa_id) is None:
        context.user_data.pop("pendente", None)
        await mensagem.reply_text("Esse registo já foi apagado.")
        return

    nome = nome[0].upper() + nome[1:]  # primeira letra em maiúscula
    # Cria a categoria nova (ou a subcategoria nova, dentro da categoria que escolheste antes)
    # e guarda logo a classificação.
    if pendente["tipo"] == "categoria":
        categoria_id = db.criar_categoria(ligacao, nome)
        subcategoria_id = None
    else:
        categoria_id = pendente["categoria_id"]
        subcategoria_id = db.criar_subcategoria(ligacao, categoria_id, nome)

    context.user_data.pop("pendente", None)
    await mensagem.reply_text(concluir(ligacao, despesa_id, categoria_id, subcategoria_id))


# ------------------------------------------------------------------------ botões


@so_dono
async def escolheu_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tocaste numa categoria (etiqueta c:<despesa>:<categoria>)."""
    query = update.callback_query
    await query.answer()  # diz ao Telegram que recebemos o toque (tira o "a carregar")
    # A etiqueta do botão é do género 'c:12:3'. Parte-se nos ':' para ficar com o número da
    # despesa (12) e o da categoria (3). O '_' ignora o 'c'.
    _, despesa_id, categoria_id = query.data.split(":")
    despesa_id, categoria_id = int(despesa_id), int(categoria_id)
    ligacao = ligacao_de(context)

    if not await despesa_existe(query, ligacao, despesa_id):
        return

    if categoria_id == 0:  # "Sem categoria"
        await query.edit_message_text(concluir(ligacao, despesa_id, None, None))
        return

    # Se a categoria tem subcategorias, pergunta qual é (com um botão 'Não tem'). Se não tem,
    # conclui logo.
    subcategorias = db.listar_subcategorias(ligacao, categoria_id)
    if not subcategorias:  # esta categoria não tem subcategorias: não pergunta mais nada
        await query.edit_message_text(concluir(ligacao, despesa_id, categoria_id, None))
        return

    # Um botão por subcategoria. A etiqueta s:despesa:categoria:subcategoria leva os três
    # números.
    botoes = [
        (nome, f"s:{despesa_id}:{categoria_id}:{subcategoria_id}")
        for subcategoria_id, nome in subcategorias
    ]
    botoes.append(("➕ Nova", f"ns:{despesa_id}:{categoria_id}"))
    botoes.append(("Não tem", f"s:{despesa_id}:{categoria_id}:0"))
    await query.edit_message_text(
        f"{resumo(ligacao, despesa_id)}\nSubcategoria?", reply_markup=teclado(botoes)
    )


@so_dono
async def escolheu_subcategoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tocaste numa subcategoria (etiqueta s:<despesa>:<categoria>:<subcategoria>)."""
    query = update.callback_query
    await query.answer()
    _, despesa_id, categoria_id, subcategoria_id = query.data.split(":")
    despesa_id, categoria_id = int(despesa_id), int(categoria_id)
    subcategoria_id = int(subcategoria_id) or None  # 0 ("Não tem") vira None
    ligacao = ligacao_de(context)

    if not await despesa_existe(query, ligacao, despesa_id):
        return
    await query.edit_message_text(concluir(ligacao, despesa_id, categoria_id, subcategoria_id))


@so_dono
async def pediu_nova_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tocaste em '➕ Nova' nas categorias. A tua próxima mensagem será o nome."""
    query = update.callback_query
    await query.answer()
    despesa_id = int(query.data.split(":")[1])
    # Lembra que a tua próxima mensagem de texto é o nome da categoria nova, e para que
    # despesa é. O user_data guarda coisas por pessoa enquanto o bot está a correr.
    context.user_data["pendente"] = {"tipo": "categoria", "despesa_id": despesa_id}
    await query.edit_message_text("Escreve o nome da nova categoria (ou 'cancelar'):")


@so_dono
async def pediu_nova_subcategoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tocaste em '➕ Nova' nas subcategorias. A tua próxima mensagem será o nome."""
    query = update.callback_query
    await query.answer()
    _, despesa_id, categoria_id = query.data.split(":")
    # Igual ao anterior, mas guarda também a categoria onde a subcategoria nova vai ficar.
    context.user_data["pendente"] = {
        "tipo": "subcategoria",
        "despesa_id": int(despesa_id),
        "categoria_id": int(categoria_id),
    }
    await query.edit_message_text("Escreve o nome da nova subcategoria (ou 'cancelar'):")


# ------------------------------------------------------------- desfazer e corrigir


@so_dono
async def desfazer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/desfazer: apaga o último registo."""
    # Apaga a despesa mais recente e devolve (valor, descrição), para te mostrar o que foi
    # apagado.
    apagada = db.apagar_ultima(ligacao_de(context))
    if apagada is None:
        await update.effective_message.reply_text("Não há nada para desfazer.")
        return
    centimos, descricao = apagada
    await update.effective_message.reply_text(f"Apagado: {euros(centimos)} ({descricao})")


@so_dono
async def corrigir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/corrigir: volta a perguntar a categoria da última despesa (e o bot reaprende a palavra)."""
    ligacao = ligacao_de(context)
    # Pega na última despesa e volta a mostrar os botões de categoria. Quando escolheres, o
    # bot reaprende a palavra.
    despesa_id = db.id_ultima_despesa(ligacao)
    if despesa_id is None:
        await update.effective_message.reply_text("Ainda não há despesas.")
        return
    await update.effective_message.reply_text(
        f"{resumo(ligacao, despesa_id)}\nEm que categoria entra?",
        reply_markup=teclado(botoes_categorias(ligacao, despesa_id)),
    )


# ------------------------------------------------------------ orçamento e aviso


@so_dono
async def orcamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/orcamento 600 define o orçamento mensal. Sem número, mostra o atual.

    O valor do aviso é orçamento x percentagem // 100, sempre em cêntimos inteiros.
    """
    mensagem = update.effective_message
    ligacao = ligacao_de(context)

    # '/orcamento' sozinho (sem número) só mostra o orçamento mensal atual.
    if not context.args:
        valor, percentagem = db.ler_orcamento(ligacao)
        if valor is None:
            await mensagem.reply_text(
                "Ainda não definiste o orçamento mensal. Usa, por exemplo: /orcamento 600"
            )
        else:
            await mensagem.reply_text(
                f"Orçamento mensal: {euros(valor)}. Aviso aos {percentagem}% "
                f"({euros(valor * percentagem // 100)}). Para mudar: /orcamento 700"
            )
        return

    # O que escreveste a seguir ao comando (o '600' de '/orcamento 600') passa para cêntimos.
    centimos = parse_valor(context.args[0])
    if centimos is None:
        await mensagem.reply_text("Não percebi o valor. Exemplo: /orcamento 600")
        return

    # Guarda o novo orçamento (e deixa o aviso disponível outra vez).
    db.definir_orcamento(ligacao, centimos)
    _, percentagem = db.ler_orcamento(ligacao)
    await mensagem.reply_text(
        f"Orçamento mensal: {euros(centimos)}. "
        f"Aviso aos {percentagem}% ({euros(centimos * percentagem // 100)})."
    )
    await avisar_se_preciso(mensagem, ligacao)  # se já passaste o novo limite, avisa logo


@so_dono
async def avisar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/avisar 80 define a percentagem a que recebes o aviso."""
    mensagem = update.effective_message
    ligacao = ligacao_de(context)

    # Só aceita um número inteiro entre 1 e 100: a percentagem do orçamento a que queres ser
    # avisado.
    if not context.args or not context.args[0].isdigit() or not 1 <= int(context.args[0]) <= 100:
        await mensagem.reply_text("Usa assim: /avisar 80  (um número de 1 a 100)")
        return

    db.definir_percentagem(ligacao, int(context.args[0]))
    valor, percentagem = db.ler_orcamento(ligacao)
    if valor is None:
        await mensagem.reply_text(
            f"Aviso aos {percentagem}%. Falta definires o orçamento mensal: /orcamento 600"
        )
        return
    await mensagem.reply_text(
        f"Aviso aos {percentagem}% ({euros(valor * percentagem // 100)} de {euros(valor)})."
    )
    await avisar_se_preciso(mensagem, ligacao)


# ---------------------------------------------------------------------- resumos


@so_dono
async def hoje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hoje: o que gastaste hoje."""
    ligacao = ligacao_de(context)
    dia = tempo.hoje()
    # De hoje (incluído) até amanhã (excluído).
    total, por_categoria = db.resumo_periodo(ligacao, dia, dia + timedelta(days=1))
    await update.effective_message.reply_text(
        formatar_resumo(f"Hoje, {dia:%d/%m}", total, por_categoria)
    )


@so_dono
async def semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/semana: cada gasto desde segunda-feira, por categoria. (O orçamento é mensal, por isso aparece no /mes.)"""
    ligacao = ligacao_de(context)
    # A semana vai de segunda a domingo: começamos pela segunda-feira desta semana.
    segunda = tempo.segunda_da_semana()
    # Todas as despesas da semana, de segunda a domingo, agrupadas por categoria.
    grupos = db.despesas_por_categoria(ligacao, segunda, segunda + timedelta(days=7))
    # enviar_longo parte o texto em várias mensagens se passar o limite do Telegram
    await enviar_longo(
        update.effective_message,
        formatar_detalhado(f"Semana desde {segunda:%d/%m}", grupos),
    )


@so_dono
async def mes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mes: cada gasto deste mês, por categoria, quanto do orçamento mensal já foi e o mês anterior."""
    ligacao = ligacao_de(context)
    primeiro = tempo.primeiro_do_mes()
    # As despesas do mês inteiro, do dia 1 ao último dia, agrupadas por categoria.
    grupos = db.despesas_por_categoria(ligacao, primeiro, tempo.primeiro_do_mes_seguinte())
    # Só o total do mês anterior inteiro, para teres uma referência.
    anterior, _ = db.resumo_periodo(ligacao, tempo.primeiro_do_mes_anterior(), primeiro)
    # O orçamento mensal (None se ainda não o definiste). O '_' ignora a percentagem do aviso.
    valor, _ = db.ler_orcamento(ligacao)
    # MESES[primeiro.month - 1]: o mês 11 (novembro) está na posição 10 da lista, porque a
    # lista começa em 0. Com orçamento definido, o total aparece como 'Total: X de Y (N%)'.
    texto_final = formatar_detalhado(f"Mês de {MESES[primeiro.month - 1]}", grupos, valor)
    texto_final += f"\n\nMês anterior: {euros(anterior)}"
    await enviar_longo(update.effective_message, texto_final)


# ------------------------------------------------------------------------ comparar


def euros_com_sinal(centimos):
    """Como o euros(), mas com sinal à frente: 1200 vira '+12,00 €' e -800 vira '-8,00 €'."""
    if centimos > 0:
        return "+" + euros(centimos)
    if centimos < 0:
        return "-" + euros(-centimos)  # o euros() espera um número positivo
    return euros(0)


def formatar_comparacao(nome_atual, nome_anterior, periodo_atual, periodo_anterior, atual, anterior):
    """Texto que compara dois períodos, por exemplo esta semana e a semana passada.

    'atual' e 'anterior' vêm de db.resumo_periodo: (total, [(categoria, cêntimos), ...]).
    Os períodos são sempre completos (segunda a domingo, ou do dia 1 ao último dia do mês).
    O atual ainda está a decorrer, por isso aparece como "em curso".
    """
    total_atual, categorias_atual = atual
    total_anterior, categorias_anterior = anterior
    cabecalho = f"Comparação: {periodo_atual} (em curso) contra {periodo_anterior}"

    # Sem nada em nenhum dos dois períodos, não há o que comparar
    if total_atual == 0 and total_anterior == 0:
        return f"{cabecalho}\n\nAinda sem despesas nestes dois períodos."

    linhas = [cabecalho, "", f"{nome_atual}: {euros(total_atual)}"]

    # Sem despesas no período anterior (por exemplo, o bot ainda é novo), não dá para comparar
    if total_anterior == 0:
        linhas.append(f"{nome_anterior}: sem despesas registadas.")
        linhas.append("")
        linhas.append("Ainda não há dados do período anterior para comparar.")
        return "\n".join(linhas)

    diferenca = total_atual - total_anterior
    # A percentagem só serve para mostrar, por isso pode usar decimais e arredondar
    percentagem = round(diferenca * 100 / total_anterior)
    texto_percentagem = f"{percentagem:+d}%" if percentagem else "0%"  # o ":+d" põe o sinal
    linhas.append(f"{nome_anterior}: {euros(total_anterior)}")
    linhas.append(f"Diferença: {euros_com_sinal(diferenca)} ({texto_percentagem})")

    # dict(...) transforma a lista de pares num dicionário {categoria: cêntimos}
    valores_atual = dict(categorias_atual)
    valores_anterior = dict(categorias_anterior)

    # Calcula a mudança de cada categoria que aparece em qualquer um dos períodos
    mudancas = []
    for nome in set(valores_atual) | set(valores_anterior):  # o "|" junta os dois conjuntos
        antes = valores_anterior.get(nome, 0)  # uma categoria sem gastos conta como 0
        agora = valores_atual.get(nome, 0)
        if agora != antes:
            mudancas.append((nome, agora - antes, antes, agora))

    # Ordena pelo tamanho da mudança (o abs ignora o sinal), da maior para a menor.
    # O nome desempata, para a ordem ser sempre a mesma.
    mudancas.sort(key=lambda mudanca: (-abs(mudanca[1]), mudanca[0]))
    if mudancas:
        linhas.append("")
        linhas.append("O que mais mudou:")
        for nome, mudanca, antes, agora in mudancas:
            linhas.append(f"{nome}: {euros_com_sinal(mudanca)} ({euros(antes)} → {euros(agora)})")
    return "\n".join(linhas)


def texto_comparar(ligacao, tipo):
    """Monta a comparação de 'semana' ou 'mes' com o período anterior.

    Compara períodos de calendário completos: a semana vai de segunda a domingo e o mês do
    dia 1 ao último dia. Se perguntares a meio (numa terça, por exemplo), o período atual
    mostra só o que já gastaste dentro dele.
    """
    if tipo == "semana":
        inicio = tempo.segunda_da_semana()
        fim = inicio + timedelta(days=7)  # o "fim" é o primeiro dia a seguir ao período
        inicio_anterior = inicio - timedelta(days=7)
        nomes = ("Esta semana", "Semana passada")
    else:
        inicio = tempo.primeiro_do_mes()
        fim = tempo.primeiro_do_mes_seguinte()
        inicio_anterior = tempo.primeiro_do_mes_anterior()
        nomes = ("Este mês", "Mês passado")

    atual = db.resumo_periodo(ligacao, inicio, fim)
    anterior = db.resumo_periodo(ligacao, inicio_anterior, inicio)

    # Para mostrar, cada período acaba no último dia, que é um dia antes do "fim"
    periodo_atual = f"{inicio:%d/%m} a {fim - timedelta(days=1):%d/%m}"
    periodo_anterior = f"{inicio_anterior:%d/%m} a {inicio - timedelta(days=1):%d/%m}"
    return formatar_comparacao(nomes[0], nomes[1], periodo_atual, periodo_anterior, atual, anterior)


@so_dono
async def comparar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/comparar: mostra os botões Semana e Mês. Também aceita /comparar semana ou /comparar mes."""
    mensagem = update.effective_message
    if context.args:
        tipo = normalizar(context.args[0])  # "Mês" e "mes" passam a ser a mesma coisa
        if tipo in ("semana", "mes"):
            await mensagem.reply_text(texto_comparar(ligacao_de(context), tipo))
            return
    # Sem argumento (ou com um que não conhecemos), mostra dois botões para escolheres o
    # período.
    botoes = [("Semana", "cmp:semana"), ("Mês", "cmp:mes")]
    await mensagem.reply_text("Comparar o quê?", reply_markup=teclado(botoes))


@so_dono
async def escolheu_comparar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tocaste em Semana ou Mês no /comparar (etiqueta cmp:semana ou cmp:mes)."""
    query = update.callback_query
    await query.answer()
    # A etiqueta é 'cmp:semana' ou 'cmp:mes'. O [1] fica com a parte depois dos ':'.
    tipo = query.data.split(":")[1]
    # Troca a pergunta 'Comparar o quê?' pela comparação. Se tocares duas vezes no mesmo
    # botão, o texto seria igual e o Telegram recusa a edição; o erro() ignora esse caso em
    # silêncio.
    await query.edit_message_text(texto_comparar(ligacao_de(context), tipo))


def texto_lista(ligacao, categoria_id):
    """Movimentos de uma categoria nesta semana. categoria_id 0 = sem categoria."""
    # Os movimentos contam-se de segunda até domingo desta semana.
    segunda = tempo.segunda_da_semana()
    # O 'categoria_id or None' troca o 0 (que quer dizer 'sem categoria') por None, que é como
    # a base de dados guarda as despesas sem categoria.
    movimentos = db.listar_movimentos(
        ligacao, categoria_id or None, segunda, segunda + timedelta(days=7)
    )
    nome = db.nome_destino(ligacao, categoria_id or None, None)
    if not movimentos:
        return f"{nome}: sem despesas esta semana."
    # Soma só os cêntimos de cada movimento. A data e a descrição ignoram-se com '_'.
    total = sum(centimos for _, _, centimos in movimentos)
    linhas = [f"{nome}, semana desde {segunda:%d/%m}"]
    mostrados = movimentos[-40:]  # só os 40 mais recentes, para a mensagem não ficar enorme
    if len(movimentos) > len(mostrados):
        linhas.append(f"(+{len(movimentos) - len(mostrados)} mais antigos)")
    for criada_em, descricao, centimos in mostrados:
        # criada_em é do género '2026-11-08 20:15:00': as 10 primeiras letras são o dia.
        dia = date.fromisoformat(criada_em[:10])
        linhas.append(f"{dia:%d/%m}  {descricao}  {euros(centimos)}")
    linhas.append(f"Total: {euros(total)}")
    return "\n".join(linhas)


@so_dono
async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lista <categoria>: movimentos dessa categoria. Sem nome, mostra botões."""
    mensagem = update.effective_message
    ligacao = ligacao_de(context)

    if not context.args:
        botoes = [(nome, f"l:{categoria_id}") for categoria_id, nome in db.listar_categorias(ligacao)]
        botoes.append(("Sem categoria", "l:0"))
        await mensagem.reply_text("De que categoria?", reply_markup=teclado(botoes))
        return

    # Junta tudo o que escreveste a seguir ao /lista, porque o nome pode ter várias palavras
    # (por exemplo '/lista jogos e subscrições').
    pedido = " ".join(context.args)
    # 'sem' ou 'sem categoria' escolhe as despesas sem categoria (o 0 é o código para isso).
    # Caso contrário procura pelo nome, e aceita só o início ('refe').
    if normalizar(pedido).startswith("sem"):
        categoria_id = 0
    else:
        categoria_id = db.encontrar_categoria(ligacao, pedido, aproximado=True)
    if categoria_id is None:
        await mensagem.reply_text("Não encontrei essa categoria. Usa /lista sem nome para escolher.")
        return
    await mensagem.reply_text(texto_lista(ligacao, categoria_id))


@so_dono
async def escolheu_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tocaste numa categoria do /lista (etiqueta l:<categoria>)."""
    query = update.callback_query
    await query.answer()
    categoria_id = int(query.data.split(":")[1])
    await query.edit_message_text(texto_lista(ligacao_de(context), categoria_id))


@so_dono
async def temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/temas: tudo o que o bot sabe (categorias, subcategorias e palavras)."""
    # Uma linha por categoria. Se só tem palavras sem subcategorias, mostra-as na mesma linha.
    # Se tem subcategorias, mostra uma linha por cada uma.
    linhas = []
    for categoria, grupos in db.temas(ligacao_de(context)):
        if not grupos:
            linhas.append(f"{categoria}: (ainda sem palavras)")
        elif len(grupos) == 1 and grupos[0][0] is None:
            linhas.append(f"{categoria}: {', '.join(grupos[0][1])}")
        else:
            linhas.append(categoria)
            for subcategoria, palavras in grupos:
                etiqueta = subcategoria or "sem subcategoria"
                linhas.append(f"  {etiqueta}: {', '.join(palavras) or '-'}")
    await enviar_longo(update.effective_message, "\n".join(linhas))


# -------------------------------------------------------------- exportar e limpar


@so_dono
async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/exportar: manda-te um ficheiro CSV com todas as despesas (abre no Excel)."""
    mensagem = update.effective_message
    despesas = db.todas_as_despesas(ligacao_de(context))
    if not despesas:
        await mensagem.reply_text("Ainda não há despesas para exportar.")
        return

    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")  # o Excel português separa com ponto e vírgula
    escritor.writerow(["data", "valor", "descricao", "categoria", "subcategoria"])
    for data, centimos, descricao, categoria, subcategoria in despesas:
        valor = f"{centimos // 100},{centimos % 100:02d}"  # 350 vira "3,50"
        escritor.writerow([data, valor, descricao, categoria, subcategoria])

    # utf-8-sig põe uma marca no início que faz o Excel ler bem os acentos
    conteudo = saida.getvalue().encode("utf-8-sig")
    await mensagem.reply_document(document=conteudo, filename="despesas.csv")


@so_dono
async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/limpar: pede confirmação antes de apagar todas as despesas."""
    botoes = [("Apagar tudo", "limpar:sim"), ("Cancelar", "limpar:nao")]
    await update.effective_message.reply_text(
        "Isto apaga TODAS as despesas registadas. As categorias, as palavras que o bot "
        "aprendeu e o orçamento ficam. Tens a certeza?",
        reply_markup=teclado(botoes),
    )


@so_dono
async def confirmou_limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta aos botões do /limpar (etiquetas limpar:sim e limpar:nao)."""
    query = update.callback_query
    await query.answer()
    # O botão 'Apagar tudo' tem a etiqueta limpar:sim, e o 'Cancelar' tem limpar:nao.
    if query.data == "limpar:sim":
        apagadas = db.limpar_despesas(ligacao_de(context))
        await query.edit_message_text(f"Feito: {apagadas} despesas apagadas.")
    else:
        await query.edit_message_text("Cancelado. Não apaguei nada.")


# ------------------------------------------------------------------------ erros


async def erro(update, context: ContextTypes.DEFAULT_TYPE):
    """Chamada quando qualquer outra função falha. Escreve o detalhe no terminal e avisa-te."""
    # Tocar duas vezes no mesmo botão faz o Telegram recusar a edição ("Message is not
    # modified"), porque o texto novo seria igual ao que já lá está. Não é um erro a sério:
    # ignora-se sem avisar.
    if isinstance(context.error, BadRequest) and "not modified" in str(context.error).lower():
        return
    logging.error("Erro ao tratar uma mensagem", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text("Algo falhou. Tenta outra vez.")
        except Exception:
            pass  # se nem isto der, já não há mais nada a fazer
