"""Base de dados (SQLite): tabelas, categorias iniciais e todas as consultas do bot."""

import os
import sqlite3
from datetime import timedelta

import tempo
from parsing import normalizar, palavras_da_descricao

# O ficheiro da base de dados fica sempre ao lado deste ficheiro,
# mesmo que arranques o bot a partir de outra pasta
CAMINHO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "despesas.db")

# O desenho da base de dados: 5 tabelas, cada uma como uma folha de Excel com uma linha por
# registo. O REFERENCES liga uma tabela à outra pelo número (id): por exemplo, cada despesa aponta
# para a sua categoria.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS subcategorias (
    id INTEGER PRIMARY KEY,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    nome TEXT NOT NULL,
    UNIQUE (categoria_id, nome)
);

-- palavra -> categoria (e subcategoria, que pode ficar vazia). As palavras guardam-se
-- já normalizadas: sem acentos, sem pontuação, em minúsculas
CREATE TABLE IF NOT EXISTS palavras (
    palavra TEXT PRIMARY KEY,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    subcategoria_id INTEGER REFERENCES subcategorias(id)
);

-- O valor guarda-se em cêntimos (número inteiro) e a data como texto 'AAAA-MM-DD HH:MM:SS'
CREATE TABLE IF NOT EXISTS despesas (
    id INTEGER PRIMARY KEY,
    centimos INTEGER NOT NULL CHECK (centimos > 0),
    descricao TEXT NOT NULL,
    categoria_id INTEGER REFERENCES categorias(id),
    subcategoria_id INTEGER REFERENCES subcategorias(id),
    criada_em TEXT NOT NULL
);

-- Guarda coisas soltas: orcamento_centimos, aviso_percentagem e aviso_semana
CREATE TABLE IF NOT EXISTS definicoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""

# categoria -> subcategoria -> palavras. A chave None quer dizer "sem subcategoria".
# Podes mudar à vontade: o bot acrescenta o que falta sempre que arranca e nunca apaga nada.
SEMENTES = {
    "Refeições": {
        "Pequeno-almoço": ["café", "torrada", "croissant", "pão", "bica", "galão"],
        "Almoço": ["almoço", "prato", "menu"],
        "Lanche": ["bolo", "sumo", "sandes"],
        "Jantar": ["jantar", "pizza", "hambúrguer", "kebab", "sushi"],
    },
    "Supermercado": {
        None: ["continente", "lidl", "pingo", "auchan", "aldi", "minipreço", "supermercado"]
    },
    "Transportes": {
        None: ["autocarro", "comboio", "gasolina", "gasóleo", "uber", "bolt", "metro",
               "táxi", "portagem", "passe"]
    },
    "Lazer": {None: ["cinema", "bar", "copo", "discoteca", "concerto", "cerveja"]},
    "Jogos e subscrições": {
        None: ["steam", "playstation", "psn", "xbox", "netflix", "spotify", "youtube", "jogo"]
    },
    "Compras": {None: ["roupa", "sapatilhas", "sapatos", "calças", "casaco", "perfume"]},
    "Estudos": {None: ["livro", "propinas", "impressão", "fotocópias", "caneta", "caderno"]},
    "Outros": {None: []},
}


def ligar(caminho=CAMINHO_DB):
    """Abre a ligação à base de dados (cria o ficheiro se ainda não existir)."""
    ligacao = sqlite3.connect(caminho)
    # O SQLite só respeita as ligações entre tabelas se pedires isto em cada ligação
    ligacao.execute("PRAGMA foreign_keys = ON")
    return ligacao


def criar_tabelas(ligacao):
    """Cria as tabelas que ainda não existem."""
    ligacao.executescript(ESQUEMA)


def semear(ligacao):
    """Cria as categorias e palavras iniciais.

    Corre sempre que o bot arranca: o INSERT OR IGNORE salta o que já existe,
    por isso nunca duplica nada nem desfaz o que o bot aprendeu contigo.
    """
    # Percorre as categorias da lista SEMENTES (lá em cima). Para cada uma: cria a categoria,
    # as subcategorias e as palavras que apontam para elas.
    for categoria, subcategorias in SEMENTES.items():
        ligacao.execute("INSERT OR IGNORE INTO categorias (nome) VALUES (?)", (categoria,))
        # Vai buscar o número (id) que a base de dados deu à categoria, porque as
        # subcategorias e as palavras ligam-se a ela por esse número.
        categoria_id = ligacao.execute(
            "SELECT id FROM categorias WHERE nome = ?", (categoria,)
        ).fetchone()[0]
        # Cada categoria tem subcategorias, e cada subcategoria as suas palavras. A chave
        # None quer dizer 'palavras ligadas só à categoria, sem subcategoria'.
        for subcategoria, palavras in subcategorias.items():
            # Começa sem subcategoria. Só passa a ter número se esta categoria tiver
            # mesmo uma.
            subcategoria_id = None
            if subcategoria is not None:
                ligacao.execute(
                    "INSERT OR IGNORE INTO subcategorias (categoria_id, nome) VALUES (?, ?)",
                    (categoria_id, subcategoria),
                )
                subcategoria_id = ligacao.execute(
                    "SELECT id FROM subcategorias WHERE categoria_id = ? AND nome = ?",
                    (categoria_id, subcategoria),
                ).fetchone()[0]
            # Guarda cada palavra já normalizada (sem acentos nem maiúsculas), que é
            # como o bot as compara quando escreves uma despesa. O INSERT OR IGNORE
            # salta as que já existem.
            for palavra in palavras:
                ligacao.execute(
                    "INSERT OR IGNORE INTO palavras (palavra, categoria_id, subcategoria_id) "
                    "VALUES (?, ?, ?)",
                    (normalizar(palavra), categoria_id, subcategoria_id),
                )
    ligacao.commit()


# ---------------------------------------------------------------- categorias


def listar_categorias(ligacao):
    """Todas as categorias, como lista de (id, nome)."""
    return ligacao.execute("SELECT id, nome FROM categorias ORDER BY id").fetchall()


def listar_subcategorias(ligacao, categoria_id):
    """As subcategorias de uma categoria, como lista de (id, nome)."""
    return ligacao.execute(
        "SELECT id, nome FROM subcategorias WHERE categoria_id = ? ORDER BY id",
        (categoria_id,),
    ).fetchall()


def encontrar_categoria(ligacao, nome, aproximado=False):
    """Procura uma categoria pelo nome, sem ligar a maiúsculas nem acentos.

    Com aproximado=True, aceita também o início do nome ('refe' encontra 'Refeições').
    Devolve o id ou None.
    """
    # Compara sempre o texto normalizado, para 'Refeições', 'refeicoes' e 'REFEIÇÕES' serem a
    # mesma categoria.
    procurado = normalizar(nome)
    categorias = listar_categorias(ligacao)
    # Primeiro procura um nome exatamente igual (depois de normalizado).
    for categoria_id, categoria_nome in categorias:
        if normalizar(categoria_nome) == procurado:
            return categoria_id
    if aproximado and procurado:
        # Só com aproximado=True: aceita um nome que comece pelo que escreveste, para
        # '/lista refe' chegar a 'Refeições'.
        for categoria_id, categoria_nome in categorias:
            if normalizar(categoria_nome).startswith(procurado):
                return categoria_id
    return None


def criar_categoria(ligacao, nome):
    """Cria uma categoria nova e devolve o id. Se já existir (mesmo nome), devolve a existente."""
    # Antes de criar, vê se já existe uma categoria com este nome (ignorando maiúsculas e
    # acentos), para nunca haver duas 'Animais'.
    existente = encontrar_categoria(ligacao, nome)
    if existente is not None:
        return existente
    # Cria a categoria. O lastrowid, que se devolve a seguir, é o número que a base de dados
    # lhe deu.
    cursor = ligacao.execute("INSERT INTO categorias (nome) VALUES (?)", (nome,))
    ligacao.commit()
    return cursor.lastrowid


def criar_subcategoria(ligacao, categoria_id, nome):
    """Cria uma subcategoria nova dentro de uma categoria e devolve o id (ou o da que já existia)."""
    # Se esta categoria já tem uma subcategoria com este nome, devolve essa em vez de criar
    # uma repetida.
    for subcategoria_id, subcategoria_nome in listar_subcategorias(ligacao, categoria_id):
        if normalizar(subcategoria_nome) == normalizar(nome):
            return subcategoria_id
    # Não existia nenhuma igual: cria a subcategoria dentro desta categoria.
    cursor = ligacao.execute(
        "INSERT INTO subcategorias (categoria_id, nome) VALUES (?, ?)", (categoria_id, nome)
    )
    ligacao.commit()
    return cursor.lastrowid


def nome_destino(ligacao, categoria_id, subcategoria_id):
    """Texto bonito para mostrar: 'Refeições › Jantar', 'Transportes' ou 'Sem categoria'."""
    if categoria_id is None:
        return "Sem categoria"
    # Procura o nome da categoria a partir do número dela. O [0] que vem depois do fetchone()
    # fica com o primeiro (e único) campo da linha.
    categoria = ligacao.execute(
        "SELECT nome FROM categorias WHERE id = ?", (categoria_id,)
    ).fetchone()[0]
    if subcategoria_id is None:
        return categoria
    # Há subcategoria: vai buscar o nome dela e junta os dois com ' › ', por exemplo
    # 'Refeições › Jantar'.
    subcategoria = ligacao.execute(
        "SELECT nome FROM subcategorias WHERE id = ?", (subcategoria_id,)
    ).fetchone()[0]
    return f"{categoria} › {subcategoria}"


# ------------------------------------------------------------------ despesas


def guardar_despesa(ligacao, centimos, descricao, categoria_id=None, subcategoria_id=None,
                    quando=None):
    """Guarda uma despesa e devolve o id dela. 'quando' é um datetime (por defeito, agora)."""
    # Se não disseste quando foi (como acontece em 'ontem 12 jantar'), usa o momento de agora.
    quando = quando or tempo.agora()
    # Guarda a despesa. Os ? são preenchidos pelo SQLite com os valores da tuple, o que evita
    # erros com textos esquisitos. A data vai escrita como texto.
    cursor = ligacao.execute(
        "INSERT INTO despesas (centimos, descricao, categoria_id, subcategoria_id, criada_em) "
        "VALUES (?, ?, ?, ?, ?)",
        (centimos, descricao, categoria_id, subcategoria_id, tempo.formatar(quando)),
    )
    ligacao.commit()  # sem o commit a despesa desaparece quando o programa fecha
    return cursor.lastrowid


def obter_despesa(ligacao, despesa_id):
    """Devolve (cêntimos, descrição, data) de uma despesa, ou None se já não existir."""
    return ligacao.execute(
        "SELECT centimos, descricao, criada_em FROM despesas WHERE id = ?", (despesa_id,)
    ).fetchone()


def id_ultima_despesa(ligacao):
    """O id da última despesa registada, ou None se não houver nenhuma."""
    # O id mais alto é o da despesa mais recente. Se não houver despesas, o MAX devolve None.
    linha = ligacao.execute("SELECT MAX(id) FROM despesas").fetchone()
    return linha[0]


def classificar_despesa(ligacao, despesa_id, categoria_id, subcategoria_id):
    """Muda a categoria (e subcategoria) de uma despesa que já existe."""
    ligacao.execute(
        "UPDATE despesas SET categoria_id = ?, subcategoria_id = ? WHERE id = ?",
        (categoria_id, subcategoria_id, despesa_id),
    )
    ligacao.commit()


def apagar_ultima(ligacao):
    """Apaga a última despesa registada e devolve (cêntimos, descrição), ou None se não há nenhuma."""
    # Escolhe a despesa com o id mais alto (a mais recente) e guarda os dados dela, para os
    # poder mostrar depois de a apagar.
    linha = ligacao.execute(
        "SELECT id, centimos, descricao FROM despesas ORDER BY id DESC LIMIT 1"
    ).fetchone()
    # Ainda não há despesas, por isso não há nada para apagar.
    if linha is None:
        return None
    ligacao.execute("DELETE FROM despesas WHERE id = ?", (linha[0],))
    ligacao.commit()
    # Se apagar te fez voltar abaixo do limite do aviso, o aviso volta a ficar disponível
    rearmar_aviso(ligacao)
    return linha[1], linha[2]


def limpar_despesas(ligacao):
    """Apaga TODAS as despesas (mantém categorias, palavras aprendidas e orçamento).

    Devolve quantas foram apagadas.
    """
    # Apaga todas as linhas da tabela despesas. As categorias e as palavras aprendidas ficam,
    # porque estão noutras tabelas.
    cursor = ligacao.execute("DELETE FROM despesas")
    apagadas = cursor.rowcount
    # A semana fica a zeros, por isso o aviso de orçamento pode voltar a disparar.
    apagar_definicao(ligacao, "aviso_semana")
    ligacao.commit()
    return apagadas


# ------------------------------------------------------------------ palavras


def aprender_palavra(ligacao, palavra, categoria_id, subcategoria_id):
    """Ensina o bot: a partir de agora, esta palavra vai para esta categoria."""
    ligacao.execute(
        # REPLACE: se a palavra já existia noutra categoria, passa para a nova
        "INSERT OR REPLACE INTO palavras (palavra, categoria_id, subcategoria_id) "
        "VALUES (?, ?, ?)",
        (palavra, categoria_id, subcategoria_id),
    )
    ligacao.commit()


def encontrar_destino(ligacao, descricao):
    """Procura na tabela palavras uma palavra da descrição.

    Devolve (categoria_id, subcategoria_id) ou None se o bot não conhecer nenhuma.
    """
    # 1. A lista já vem limpa: sem acentos, sem pontuação e sem palavras como "uma" ou "de".
    #    Assim "Uma Pizza!" chega aqui como ["pizza"], e é isso que está guardado na tabela.
    for palavra in palavras_da_descricao(descricao):
        # 2. Procura esta palavra na tabela. O "?" é preenchido com segurança pelo SQLite,
        #    e o valor vai numa tuple, (palavra,), com a vírgula, mesmo sendo só um.
        linha = ligacao.execute(
            "SELECT categoria_id, subcategoria_id FROM palavras WHERE palavra = ?",
            (palavra,),
        ).fetchone()  # fetchone() devolve uma linha (um par) ou None se a palavra não existir

        # 3. Se o bot conhece a palavra, devolve já o par e pára. Ganha a primeira que for
        #    encontrada: em "uber eats" ganha "uber" (Transportes), por isso o /corrigir existe.
        if linha is not None:
            return linha

    # 4. Este return fica FORA do ciclo: só chegamos aqui se nenhuma palavra era conhecida.
    #    O bot vai então perguntar-te a categoria com os botões.
    return None


def temas(ligacao):
    """Tudo o que o bot sabe, para o /temas.

    Devolve uma lista de (categoria, grupos), em que grupos é uma lista de
    (nome da subcategoria ou None, lista de palavras).
    """
    # Para cada categoria monta a lista dos grupos de palavras: primeiro as que estão ligadas
    # só à categoria, depois as de cada subcategoria.
    resultado = []
    for categoria_id, categoria_nome in listar_categorias(ligacao):
        grupos = []
        # Palavras ligadas só à categoria, sem subcategoria (por isso o None).
        so_categoria = _palavras_de(ligacao, categoria_id, None)
        if so_categoria:
            grupos.append((None, so_categoria))
        # Depois, as palavras de cada subcategoria desta categoria.
        for subcategoria_id, subcategoria_nome in listar_subcategorias(ligacao, categoria_id):
            grupos.append(
                (subcategoria_nome, _palavras_de(ligacao, categoria_id, subcategoria_id))
            )
        resultado.append((categoria_nome, grupos))
    return resultado


def _palavras_de(ligacao, categoria_id, subcategoria_id):
    """Palavras ligadas a uma categoria e subcategoria. O 'IS' também funciona com valores vazios."""
    linhas = ligacao.execute(
        "SELECT palavra FROM palavras WHERE categoria_id = ? AND subcategoria_id IS ? "
        "ORDER BY palavra",
        (categoria_id, subcategoria_id),
    ).fetchall()
    # Cada linha chega como uma tuple com um só valor (a palavra). O [0] tira-a de lá, e fica
    # uma lista simples de palavras.
    return [linha[0] for linha in linhas]


# ---------------------------------------------------------------- definições


def obter_definicao(ligacao, chave, padrao=None):
    """Lê uma definição (texto). Se não existir, devolve o valor 'padrao'."""
    linha = ligacao.execute(
        "SELECT valor FROM definicoes WHERE chave = ?", (chave,)
    ).fetchone()
    # Se a definição existe, devolve o valor guardado (o campo [0]). Se não, devolve o valor
    # por defeito.
    return linha[0] if linha else padrao


def guardar_definicao(ligacao, chave, valor):
    """Guarda (ou substitui) uma definição."""
    ligacao.execute(
        "INSERT OR REPLACE INTO definicoes (chave, valor) VALUES (?, ?)", (chave, str(valor))
    )
    ligacao.commit()


def apagar_definicao(ligacao, chave):
    """Apaga uma definição, se existir."""
    ligacao.execute("DELETE FROM definicoes WHERE chave = ?", (chave,))
    ligacao.commit()


# ------------------------------------------------------ orçamento e aviso


def ler_orcamento(ligacao):
    """Devolve (orçamento em cêntimos ou None, percentagem do aviso). Por defeito aviso aos 80%."""
    # O orçamento e a percentagem estão guardados como texto na tabela definicoes. O int()
    # converte-os para números.
    orcamento = obter_definicao(ligacao, "orcamento_centimos")
    percentagem = int(obter_definicao(ligacao, "aviso_percentagem", "80"))
    # Sem orçamento definido devolve None (e não 0), para o bot saber que ainda falta
    # defini-lo.
    return (int(orcamento) if orcamento else None), percentagem


def definir_orcamento(ligacao, centimos):
    """Define o orçamento semanal. Apaga o 'já avisei', para o novo limite poder avisar já."""
    guardar_definicao(ligacao, "orcamento_centimos", centimos)
    apagar_definicao(ligacao, "aviso_semana")


def definir_percentagem(ligacao, percentagem):
    """Define a percentagem do aviso (1 a 100). Também deixa o aviso disponível outra vez."""
    guardar_definicao(ligacao, "aviso_percentagem", percentagem)
    apagar_definicao(ligacao, "aviso_semana")


def gasto_da_semana(ligacao):
    """Quanto gastaste desde segunda-feira (em cêntimos)."""
    # A semana vai de segunda a domingo: o resumo conta desde esta segunda (incluída) até à
    # segunda seguinte (excluída). O [0] no fim fica só com o total.
    segunda = tempo.segunda_da_semana()
    return resumo_periodo(ligacao, segunda, segunda + timedelta(days=7))[0]


def verificar_aviso(ligacao):
    """Diz se está na hora de avisar do orçamento.

    Devolve (gasto, orçamento, percentagem) se a semana passou a percentagem e ainda
    não avisámos nesta semana. Caso contrário devolve None. Só avisa uma vez por semana.
    """
    orcamento, percentagem = ler_orcamento(ligacao)
    # Sem orçamento definido não há nada a avisar.
    if not orcamento:
        return None
    # A data da segunda-feira serve de etiqueta da semana: guarda-se em que semana já
    # avisámos, para não repetir o aviso.
    segunda = tempo.segunda_da_semana().isoformat()
    if obter_definicao(ligacao, "aviso_semana") == segunda:
        return None  # já avisámos esta semana
    gasto = gasto_da_semana(ligacao)
    # Contas com inteiros (sem dividir) para não haver erros de arredondamento
    if gasto * 100 < orcamento * percentagem:
        return None
    # Vai avisar: regista que esta semana já foi avisada e devolve os números para a mensagem.
    guardar_definicao(ligacao, "aviso_semana", segunda)
    return gasto, orcamento, percentagem


def rearmar_aviso(ligacao):
    """Se voltaste abaixo do limite (por exemplo com /desfazer), o aviso fica disponível outra vez."""
    orcamento, percentagem = ler_orcamento(ligacao)
    if not orcamento:
        return
    # Voltou a ficar abaixo do limite: apaga a marca de 'já avisei', para o aviso poder
    # disparar outra vez.
    if gasto_da_semana(ligacao) * 100 < orcamento * percentagem:
        apagar_definicao(ligacao, "aviso_semana")


# ---------------------------------------------------------------- relatórios


def resumo_periodo(ligacao, inicio, fim):
    """Total e valor por categoria entre duas datas (o 'fim' não conta).

    Devolve (total em cêntimos, lista de (categoria, cêntimos) da maior para a menor).
    """
    # Comparar textos funciona porque as datas estão escritas de forma ordenável
    inicio, fim = inicio.isoformat(), fim.isoformat()
    # Soma todos os gastos do período. O COALESCE devolve 0 quando não há nenhum, em vez de
    # None.
    total = ligacao.execute(
        "SELECT COALESCE(SUM(centimos), 0) FROM despesas WHERE criada_em >= ? AND criada_em < ?",
        (inicio, fim),
    ).fetchone()[0]
    # LEFT JOIN mantém as despesas sem categoria, o COALESCE dá-lhes o nome "Sem categoria"
    # e o GROUP BY soma os cêntimos de cada categoria
    por_categoria = ligacao.execute(
        "SELECT COALESCE(c.nome, 'Sem categoria'), SUM(d.centimos) "
        "FROM despesas d LEFT JOIN categorias c ON c.id = d.categoria_id "
        "WHERE d.criada_em >= ? AND d.criada_em < ? "
        "GROUP BY c.id ORDER BY SUM(d.centimos) DESC, c.nome",
        (inicio, fim),
    ).fetchall()
    return total, por_categoria


def despesas_por_categoria(ligacao, inicio, fim):
    """Todas as despesas entre duas datas (o 'fim' não conta), agrupadas por categoria.

    Devolve uma lista de (categoria, total em cêntimos, movimentos), da categoria com mais
    gastos para a que tem menos. Cada movimento é (data, descrição, cêntimos), do mais antigo
    para o mais recente.
    """
    # LEFT JOIN: as despesas sem categoria também entram, com o nome "Sem categoria"
    linhas = ligacao.execute(
        "SELECT COALESCE(c.nome, 'Sem categoria'), d.criada_em, d.descricao, d.centimos "
        "FROM despesas d LEFT JOIN categorias c ON c.id = d.categoria_id "
        "WHERE d.criada_em >= ? AND d.criada_em < ? "
        "ORDER BY d.criada_em, d.id",
        (inicio.isoformat(), fim.isoformat()),
    ).fetchall()

    # Junta as despesas de cada categoria num dicionário: {nome da categoria: [movimentos]}
    grupos = {}
    for nome, criada_em, descricao, centimos in linhas:
        grupos.setdefault(nome, []).append((criada_em, descricao, centimos))

    # Monta (categoria, total, movimentos) e ordena pelo total, do maior para o menor.
    # O "-total" inverte a ordem; o nome desempata categorias com o mesmo total.
    resultado = [
        (nome, sum(centimos for _, _, centimos in movimentos), movimentos)
        for nome, movimentos in grupos.items()
    ]
    resultado.sort(key=lambda grupo: (-grupo[1], grupo[0]))
    return resultado


def listar_movimentos(ligacao, categoria_id, inicio, fim):
    """Movimentos de uma categoria (None = sem categoria) entre duas datas.

    Devolve uma lista de (data, descrição, cêntimos), do mais antigo para o mais recente.
    """
    # Usa-se "IS" e não "=" porque a categoria pode ser None (sem categoria),
    # e com "=" o SQLite nunca encontraria despesas sem categoria
    return ligacao.execute(
        "SELECT criada_em, descricao, centimos FROM despesas "
        "WHERE categoria_id IS ? AND criada_em >= ? AND criada_em < ? "
        "ORDER BY criada_em, id",
        (categoria_id, inicio.isoformat(), fim.isoformat()),
    ).fetchall()


def todas_as_despesas(ligacao):
    """Todas as despesas, para o /exportar: (data, cêntimos, descrição, categoria, subcategoria)."""
    # LEFT JOIN: as despesas sem categoria ou subcategoria também saem, com o campo vazio
    return ligacao.execute(
        "SELECT d.criada_em, d.centimos, d.descricao, COALESCE(c.nome, ''), COALESCE(s.nome, '') "
        "FROM despesas d "
        "LEFT JOIN categorias c ON c.id = d.categoria_id "
        "LEFT JOIN subcategorias s ON s.id = d.subcategoria_id "
        "ORDER BY d.id"
    ).fetchall()


if __name__ == "__main__":
    # Correr "python db.py" mostra as palavras que o bot conhece
    ligacao = ligar()
    criar_tabelas(ligacao)
    semear(ligacao)
    for categoria, grupos in temas(ligacao):
        print(categoria, grupos)
    ligacao.close()
