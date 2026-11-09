"""Datas e horas do bot. Tudo em hora de Lisboa."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# O Windows não traz a base de fusos horários que o Python usa. É por isso que o
# requirements.txt inclui o pacote "tzdata". Se ele faltar, em vez de o bot falhar,
# usamos a hora do computador (que em Portugal é a de Lisboa).
try:
    FUSO = ZoneInfo("Europe/Lisbon")
except ZoneInfoNotFoundError:
    FUSO = None


def agora():
    """Data e hora atuais em Lisboa, sem o fuso agarrado (para guardar como texto simples)."""
    if FUSO is None:
        return datetime.now()
    # Pede a hora de Lisboa e tira-lhe o fuso horário, para ficar uma data simples que se pode
    # guardar como texto.
    return datetime.now(FUSO).replace(tzinfo=None)


def hoje():
    """O dia de hoje em Lisboa."""
    return agora().date()


def formatar(momento):
    """Transforma um datetime no texto que se guarda na base de dados: '2026-11-08 20:15:00'."""
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def segunda_da_semana(dia=None):
    """A segunda-feira da semana do dia dado (ou de hoje). weekday() dá 0 à segunda."""
    dia = dia or hoje()
    # weekday() dá 0 à segunda, 1 à terça, até 6 ao domingo. Tirar esses dias leva-nos sempre
    # de volta à segunda-feira dessa semana.
    return dia - timedelta(days=dia.weekday())


def primeiro_do_mes(dia=None):
    """O dia 1 do mês do dia dado (ou de hoje)."""
    dia = dia or hoje()
    return dia.replace(day=1)


def primeiro_do_mes_seguinte(dia=None):
    """Dia 1 do mês seguinte. Truque: o dia 28 mais 4 dias cai sempre no mês seguinte."""
    dia = dia or hoje()
    # Vai para o dia 28 (que existe em todos os meses), soma 4 dias para cair sempre no mês
    # seguinte e volta ao dia 1 desse mês.
    return (dia.replace(day=28) + timedelta(days=4)).replace(day=1)


def primeiro_do_mes_anterior(dia=None):
    """Dia 1 do mês anterior. Tira-se um dia ao dia 1 (cai no mês anterior) e volta-se ao dia 1."""
    primeiro = primeiro_do_mes(dia)
    # O dia 1 menos um dia é o último dia do mês anterior. Mudando o dia para 1, ficamos no
    # primeiro dia desse mês.
    return (primeiro - timedelta(days=1)).replace(day=1)
