# Bot de despesas (Telegram)

Bot pessoal para registar despesas no Telegram. Escreves `3,5 café` e ele guarda o valor,
descobre a categoria sozinho (ou pergunta-te por botões e aprende) e mostra resumos,
comparações semana a semana e um aviso quando te aproximas do orçamento do mês
(`/orcamento 600` define o orçamento mensal; `/mes` mostra quanto já gastaste dele).

Feito em Python com `python-telegram-bot` e SQLite. Só responde ao dono (o teu ID no `.env`).

## Ficheiros

| Ficheiro | Para que serve |
|---|---|
| `bot.py` | Arranca o bot **no PC** e liga cada comando à sua função |
| `handlers.py` | O que o bot responde a cada mensagem, comando e botão |
| `db.py` | A base de dados (SQLite): tabelas e consultas |
| `parsing.py` | Lê o texto (`3,5 café`, `ontem 12 jantar`) |
| `tempo.py` | Datas e horas de Lisboa; semana de segunda a domingo |
| `servidor_web.py` | Arranca o bot **no alojamento** (modo webhook) |
| `pagina_vagas.py` | A página `/vagas` do vigia de estágios, com palavra-passe (ver Passo D) |
| `vagas_icone.png` | O ícone da app no ecrã principal do iPhone |
| `configurar_webhook.py` | Liga ou desliga o webhook no Telegram |
| `test_*.py` | Testes. Corre-se cada um com `python test_xxx.py` |
| `.env` | **Segredos** (token, ID). Nunca vai para o GitHub |
| `.env.example` | Modelo do `.env`, sem valores verdadeiros |
| `requirements.txt` | Bibliotecas para o PC |
| `requirements-web.txt` | Bibliotecas para o alojamento (as do PC mais o Flask) |

## Usar no PC

1. `.env` com `BOT_TOKEN=` (o token completo do @BotFather) e `MEU_ID=` (o número que o `/id` mostra).
2. `python bot.py` (ou duplo clique em `iniciar.bat`). O bot só responde enquanto a janela estiver aberta.
3. Testes: `python test_parsing.py`, `python test_db.py`, `python test_handlers.py`.

---

## Passo A: pôr o código no GitHub

O GitHub guarda o **código** e o histórico das mudanças. Não corre o bot, mas é de lá que o
alojamento vai buscar o código.

1. Instala o Git (git-scm.com, instalação normal). Fecha e volta a abrir o VS Code.
2. Cria uma conta em github.com.
3. No terminal do VS Code, dentro da pasta do projeto:

```
git config --global user.name "O Teu Nome"
git config --global user.email "o-teu-email"
git init -b main
git add .
git status
```

4. **Antes de continuares, lê o resultado do `git status`.** Não podem aparecer `.env`, `despesas.db`
   nem `.venv`. Se aparecer algum, **pára** e fala comigo (o `.gitignore` devia tê-los escondido).
5. Se estiver tudo certo:

```
git commit -m "Bot de despesas"
```

6. No GitHub, cria um repositório novo (botão **New**), com o nome `Bot-Despesas`. Não marques
   nenhuma das opções "Add a README / .gitignore". O repositório pode ser público, porque os segredos
   nunca saem do teu PC.
7. O GitHub mostra dois comandos para um repositório existente. Copia-os para o terminal:
   `git remote add origin ...` e `git push -u origin main`. Se pedir login, usa o browser.

Depois de cada mudança no código: `git add .`, `git commit -m "o que mudaste"`, `git push`.

---

## Passo B: pôr o bot a correr sem o PC (PythonAnywhere, plano gratuito)

### Como funciona

No PC, o bot fica a perguntar ao Telegram se há mensagens. No alojamento, o Telegram é que **envia
cada mensagem para um endereço na internet** (isto chama-se *webhook*) e o `servidor_web.py` responde.
Não é preciso nenhum programa ligado 24 horas.

### Limites do plano gratuito (confirmados em novembro de 2026; podem mudar)

- 1 aplicação web, com **validade de 1 mês**: tens de carregar num botão uma vez por mês (ver Passo C).
- 512 MiB de disco (os ficheiros, incluindo a base de dados, ficam guardados lá).
- 100 segundos de CPU (a contagem é diária, até onde sei; confirma na página de preços deles). Para uma
  pessoa a registar despesas deve chegar, mas se passares disso o bot fica mais lento.
- A conta gratuita só liga a sites de uma lista. O `api.telegram.org` está lá.

### Os passos

1. **Conta**: em pythonanywhere.com cria uma conta gratuita (*Beginner*). O nome de utilizador faz parte
   do endereço: `TEUUTILIZADOR.pythonanywhere.com` (ou `.eu.pythonanywhere.com` se escolheres o servidor europeu).
2. **Código**: separador **Consoles** → **Bash**. Descarrega o projeto do GitHub:

```
git clone https://github.com/O_TEU_UTILIZADOR/Bot-Despesas.git
cd Bot-Despesas
```

3. **Bibliotecas**: vê que versões de Python existem com `ls /usr/bin/python3*`. Usa uma 3.10 ou mais recente
   (aqui, 3.12 como exemplo) e cria o ambiente:

```
python3.12 -m venv ~/venv-despesas
~/venv-despesas/bin/pip install -r requirements-web.txt
```

4. **Segredos**: gera o segredo do webhook com este comando e **copia o resultado** (não o mostres a ninguém):

```
~/venv-despesas/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

   Depois cria o ficheiro `.env` **no alojamento** com `nano .env` (guardar: `Ctrl+O`, `Enter`; sair: `Ctrl+X`),
   com este conteúdo (vê o `.env.example`):

```
BOT_TOKEN=o token completo
MEU_ID=o teu número
WEBHOOK_SECRET=o segredo que acabaste de gerar
WEBHOOK_URL=https://TEUUTILIZADOR.pythonanywhere.com/webhook
PROXY_URL=http://proxy.server:3128
```

5. **Site**: separador **Web** → **Add a new web app** → **Manual configuration** → escolhe a **mesma versão de
   Python** do passo 3. Na página que abre:
   - **Virtualenv**: `/home/TEUUTILIZADOR/venv-despesas`
   - **WSGI configuration file**: abre-o, apaga tudo e cola isto:

```python
import sys

pasta = "/home/TEUUTILIZADOR/Bot-Despesas"
if pasta not in sys.path:
    sys.path.insert(0, pasta)

from servidor_web import application
```

   - Carrega em **Reload** (botão verde). Abre `https://TEUUTILIZADOR.pythonanywhere.com/` no browser:
     deve aparecer "O bot de despesas está ligado.".
6. **Avisar o Telegram**: na consola Bash, dentro de `Bot-Despesas`:

```
~/venv-despesas/bin/python configurar_webhook.py
```

   Deve escrever "Webhook ligado em: ...". Isto também põe o menu de comandos.
7. **Testa**: no Telegram escreve `/id` e depois `3,5 café`.

### Regras importantes

- **Só um modo de cada vez.** Enquanto o webhook estiver ligado, o bot do PC não pode correr ao mesmo tempo
  (o Telegram só entrega as mensagens a um sítio). Para voltares a usar o PC, corre
  `python configurar_webhook.py apagar` no alojamento antes do `python bot.py`. Para voltar ao alojamento,
  corre `python configurar_webhook.py` outra vez.
- **O PC e o alojamento têm bases de dados diferentes.** O `despesas.db` não vai para o GitHub (de propósito),
  por isso o alojamento começa limpo, sem os testes que fizeste no PC.
- **Atualizar o código**: no PC `git push`; no alojamento, na consola `cd ~/Bot-Despesas && git pull`
  e depois **Reload** no separador Web.

---

## Passo C: manutenção

- **Todos os meses**: separador **Web** → botão **Run until 1 month from today** (ou parecido).
  Se te esqueceres, o bot pára de responder; basta carregar no botão para voltar.
- **Cópia de segurança**: de vez em quando escreve `/exportar` no bot e guarda o ficheiro CSV.
- **Se o bot não responder**: separador Web → **Log files** → **Error log**. Os erros mais comuns:

| O que vês | Causa provável |
|---|---|
| `Falta WEBHOOK_SECRET no ficheiro .env` | O `.env` do alojamento está incompleto |
| `ModuleNotFoundError` | O **Virtualenv** da aba Web está vazio ou errado |
| Nada responde, sem erros | Corre `configurar_webhook.py`: mostra o "Último erro" do Telegram |
| `Conflict ... getUpdates` | Estás a correr o `bot.py` com o webhook ligado (ver "Só um modo") |
| Erro de ligação / `proxy` | Confirma `PROXY_URL=http://proxy.server:3128` no `.env` |
| `A página de vagas não arrancou` | Falta o `pagina_vagas.py` ou tem um erro; o bot continua a funcionar sem a página |

---

## Passo D: a página de vagas do vigia (`/vagas`)

A conta gratuita só tem **um** site, e é este. Por isso a página do vigia de estágios
(`vagas.html`) também vive aqui, no endereço `https://TEUUTILIZADOR.pythonanywhere.com/vagas`,
protegida por palavra-passe. No iPhone, "Adicionar ao ecrã principal" transforma-a numa app.

- **Como chega a página:** a cada execução, o GitHub (repositório `vigia-estagios`) envia o
  `vagas.html` para a pasta `~/dados-vigia` desta conta, pela API do PythonAnywhere.
- **A palavra-passe** fica no ficheiro `~/vagas_senha.txt`, que crias tu na consola Bash. Não vai
  para o GitHub nem para o código. Com menos de 12 caracteres a página recusa-se a abrir. Para a
  mudar, edita o ficheiro: todos os aparelhos têm de voltar a entrar.
- **Segurança:** depois de 10 tentativas erradas em 10 minutos o formulário bloqueia 10 minutos; o
  cookie dura 90 dias, só viaja por HTTPS e não se vê pelo JavaScript. Liga **Force HTTPS** no
  separador Web.
- **Não mexe no bot:** são rotas à parte (`/vagas...`). O `/webhook` fica igual, e o
  `servidor_web.py` liga a página dentro de um `try/except`, por isso se a página falhar o bot
  continua a responder (o erro aparece no Error log).
- **Atualizar:** `git pull` na consola e **Reload** no separador Web, como de costume.
- O passo a passo completo (palavra-passe, token da API, segredo no GitHub) está no README do vigia,
  na secção "Abrir no iPhone como uma app". Testes: `python test_vagas.py`.
