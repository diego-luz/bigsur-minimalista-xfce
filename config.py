"""Preferencias do usuario.

Um unico arquivo JSON, com valores validados contra uma tabela de opcoes. A
validacao serve tanto para o terminal quanto para a pagina web: qualquer valor
que nao esteja na tabela e recusado antes de chegar ao motor.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import caminhos


class Opcao:
    """Uma preferencia: o que ela aceita, o padrao e para que serve."""

    def __init__(self, chave: str, padrao: str, valores: tuple[str, ...],
                 titulo: str, ajuda: str = "", livre: str = "") -> None:
        self.chave = chave
        self.padrao = padrao
        self.valores = valores
        self.titulo = titulo
        self.ajuda = ajuda
        # expressao que descreve os valores aceitos alem da lista; vazia
        # significa que so a lista vale
        self.livre = livre

    def valida(self, valor: Any) -> bool:
        if not isinstance(valor, str) or not valor:
            return False
        if valor in self.valores:
            return True
        return bool(self.livre) and bool(re.fullmatch(self.livre, valor))

    def como_dict(self) -> dict:
        return {"chave": self.chave, "padrao": self.padrao,
                "valores": list(self.valores), "titulo": self.titulo,
                "ajuda": self.ajuda, "livre": bool(self.livre)}


SIM_NAO = ("sim", "nao")

OPCOES: tuple[Opcao, ...] = (
    Opcao("tema", "escuro", ("claro", "escuro"),
          "Tema", "Cor das janelas e da barra do topo"),
    Opcao("destaque", "padrao",
          ("padrao", "azul", "roxo", "rosa", "vermelho", "laranja", "amarelo", "verde", "cinza"),
          "Cor de destaque", "Cor dos botoes e da selecao"),
    Opcao("logo", "debian",
          ("debian", "debian-cor", "tux", "tux-cor"),
          "Logo do canto", "Botao que abre o menu de aplicativos"),
    Opcao("janelas", "sim", SIM_NAO,
          "Encaixe de janelas",
          "Super e setas para metades, Super+1 a 4 para quartos, layouts no Super+Z e "
          "bordas mais largas; respeita o espaco das ilhas"),
    # vindos do oasis-xfce; desligados, a barra continua a de sempre
    Opcao("ilhas", "nao", SIM_NAO,
          "Barra em ilhas",
          "A barra do topo solta da borda, com cantos redondos, e um dock com as "
          "janelas abertas numa ilha embaixo"),
    Opcao("efeitos", "desligado", ("desligado", "sombras", "desfoque"),
          "Efeitos (picom)",
          "Sombras e cantos redondos nas janelas, e desfoque atras do que e translucido. "
          "Sem aceleracao de video (VM sem 3D) o picom roda leve, sem desfoque"),
    # numa maquina recem instalada nao ha papel de parede a preservar, entao o
    # padrao e o do tema; quem ja escolheu o seu troca para "manter"
    # alem de manter e do-tema, aceita o nome de um arquivo da galeria
    Opcao("papel_de_parede", "do-tema", ("do-tema", "manter"),
          "Papel de parede", "Escolha um da galeria, ou mantenha o seu",
          livre=r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}"),
    # tela de login: alem de desktop e do-tema, aceita um nome da galeria
    Opcao("login_fundo", "desktop", ("desktop", "do-tema"),
          "Fundo da tela de login", "O mesmo do desktop, ou um da galeria",
          livre=r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}"),
    Opcao("login_desfoque", "sim", SIM_NAO,
          "Fundo desfocado", "A imagem fica embacada atras dos campos, como no macOS"),
    Opcao("login_usuarios", "campos", ("campos", "lista"),
          "Como entrar", "Digitar nome e senha, ou escolher o usuario numa lista"),
    # o padrao repete o que o Debian ja faz com o light-locker: a tela apaga
    # aos dez minutos e bloqueia logo depois
    Opcao("bloqueio", "10", ("nao", "5", "10", "15", "30"),
          "Bloqueio de tela", "Pede a senha depois de minutos parado e ao suspender"),
)

POR_CHAVE = {o.chave: o for o in OPCOES}


def padroes() -> dict[str, str]:
    return {o.chave: o.padrao for o in OPCOES}


def ler() -> dict[str, str]:
    """Config do usuario por cima dos padroes, ignorando lixo."""
    valores = padroes()
    try:
        salvo = json.loads(caminhos.CONFIG.read_text())
    except (OSError, json.JSONDecodeError):
        return valores
    if not isinstance(salvo, dict):
        return valores
    for chave, valor in salvo.items():
        opcao = POR_CHAVE.get(chave)
        if opcao and opcao.valida(valor):
            valores[chave] = valor
    return valores


def gravar(novos: dict[str, Any]) -> list[str]:
    """Grava so o que e valido e mudou. Devolve as chaves alteradas."""
    atual = ler()
    mudou = []
    for chave, valor in novos.items():
        opcao = POR_CHAVE.get(chave)
        if opcao and opcao.valida(valor) and atual.get(chave) != valor:
            atual[chave] = valor
            mudou.append(chave)
    if mudou:
        caminhos.preparar()
        caminhos.escrever(caminhos.CONFIG, json.dumps(atual, ensure_ascii=False, indent=2) + "\n")
    return mudou


def filtrar(bruto: dict[str, Any]) -> dict[str, str]:
    """So as chaves conhecidas e com valor aceito."""
    return {c: v for c, v in bruto.items()
            if c in POR_CHAVE and POR_CHAVE[c].valida(v)}
