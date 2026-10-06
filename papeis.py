"""Galeria de papeis de parede.

Os arquivos vem do repositorio de papeis do WhiteSur, baixado pela receita 33,
e ficam na pasta de imagens de fundo do usuario. Aqui so listamos, geramos
miniatura e resolvemos qual usar.

Antes da instalacao a pasta ainda nao existe, entao o pacote traz uma
miniatura de cada papel em recursos/web/papeis. A escolha e guardada pelo
nome, e o contexto e refeito a cada receita: quando a aparencia roda, o
arquivo com esse nome ja foi baixado. Para refazer as miniaturas depois de
baixar uma versao nova do repositorio:

    for f in ~/.local/share/backgrounds/WhiteSur/*; do
      convert "$f" -resize 320x -strip -quality 78 \\
        "recursos/web/papeis/$(basename "${f%.*}").jpg"
    done
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import caminhos

PASTA = Path.home() / ".local/share/backgrounds/WhiteSur"
CATALOGO = caminhos.WEB / "papeis"
EXTENSOES = (".jpg", ".jpeg", ".png")
NOME_VALIDO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")

# quando o usuario deixa a escolha por conta do tema, esta e a ordem de
# preferencia. As variantes "-dark" do WhiteSur sao cinzas quase pretas, entao
# para o tema escuro preferimos as coloridas, que ficam melhor.
PREFERENCIA = {
    "escuro": ("WhiteSur", "WhiteSur-morning", "Monterey", "WhiteSur-dark"),
    "claro": ("WhiteSur-light", "WhiteSur-morning", "WhiteSur", "Monterey-light"),
}


def _listar(pasta: Path) -> list[dict]:
    if not pasta.is_dir():
        return []
    saida = []
    for arquivo in sorted(pasta.iterdir()):
        if arquivo.suffix.lower() not in EXTENSOES or not arquivo.is_file():
            continue
        if not NOME_VALIDO.fullmatch(arquivo.stem):
            continue
        saida.append({"nome": arquivo.stem, "arquivo": arquivo.name,
                      "escuro": "dark" in arquivo.stem.lower()})
    return saida


def baixados() -> bool:
    """Os papeis ja chegaram na maquina?"""
    return bool(_listar(PASTA))


def disponiveis() -> list[dict]:
    """Os papeis de parede, em ordem alfabetica: os baixados ou, antes do
    download, os do catalogo que vem no pacote."""
    return _listar(PASTA) or _listar(CATALOGO)


def caminho(nome: str) -> Path | None:
    """O arquivo de um papel de parede, se o nome for seguro e existir."""
    if not nome or not NOME_VALIDO.fullmatch(nome):
        return None
    for ext in EXTENSOES:
        alvo = PASTA / f"{nome}{ext}"
        if alvo.is_file() and alvo.parent == PASTA:
            return alvo
    return None


def nome_escolhido(cfg: dict[str, str]) -> str | None:
    """Qual papel usar, pelo nome; vale tambem antes do download."""
    valor = cfg.get("papel_de_parede", "do-tema")
    if valor == "manter":
        return None
    todos = disponiveis()
    existentes = {p["nome"] for p in todos}
    # um nome que sumiu do repositorio cai na preferencia do tema
    if valor != "do-tema" and valor in existentes:
        return valor
    for nome in PREFERENCIA.get(cfg.get("tema", "escuro"), ()):
        if nome in existentes:
            return nome
    return todos[0]["nome"] if todos else None


def escolhido(cfg: dict[str, str]) -> Path | None:
    """Qual arquivo usar, conforme a preferencia. None quer dizer nao mexer,
    inclusive quando as imagens ainda nao foram baixadas."""
    nome = nome_escolhido(cfg)
    return caminho(nome) if nome else None


def do_desktop() -> Path | None:
    """O arquivo que o xfdesktop mostra agora, inclusive o que veio de fora da galeria."""
    try:
        saida = subprocess.run(["xfconf-query", "-c", "xfce4-desktop", "-lv"],
                               capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    # as chaves com workspace0 sao as do monitor ligado; as outras costumam ser
    # restos de monitores antigos
    candidatos = []
    for linha in saida.splitlines():
        chave, _, valor = linha.partition(" ")
        if chave.endswith("/last-image"):
            candidatos.append((0 if "/workspace0/" in chave else 1, valor.strip()))
    for _, valor in sorted(candidatos):
        if valor and Path(valor).is_file():
            return Path(valor)
    return None


def fundo_login(cfg: dict[str, str]) -> Path | None:
    """A imagem de origem do fundo da tela de login."""
    valor = cfg.get("login_fundo", "desktop")
    if valor == "do-tema":
        return escolhido({**cfg, "papel_de_parede": "do-tema"})
    if valor != "desktop":
        direto = caminho(valor)
        if direto:
            return direto
    # "desktop": o que a aparencia vai aplicar, ou, se ela mantem o do usuario,
    # o que ja esta na tela
    return escolhido(cfg) or do_desktop()


def miniatura(nome: str, largura: int = 320) -> Path | None:
    """Miniatura em cache de um papel da galeria; antes do download, a do pacote."""
    origem = caminho(nome)
    if origem:
        return _miniatura(origem, nome, largura)
    if not NOME_VALIDO.fullmatch(nome or ""):
        return None
    pronta = CATALOGO / f"{nome}.jpg"
    return pronta if pronta.is_file() else None


def _miniatura(origem: Path, chave: str, largura: int) -> Path | None:
    """Gera na primeira vez, depois so le."""
    destino = caminhos.DADOS_DIR / "miniaturas" / f"{chave}.jpg"
    if destino.is_file() and destino.stat().st_mtime >= origem.stat().st_mtime:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        pronto = subprocess.run(
            ["convert", str(origem), "-resize", f"{largura}x", "-quality", "80",
             str(destino)], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pronto = False
    if pronto and destino.is_file():
        return destino
    return origem          # sem ImageMagick, serve o arquivo inteiro
