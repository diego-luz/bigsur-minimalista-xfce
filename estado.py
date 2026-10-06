"""O que ja foi aplicado, o registro e as copias de seguranca."""

from __future__ import annotations

import datetime as _dt
import shutil
import subprocess
from pathlib import Path

from . import caminhos


def _agora() -> str:
    return _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def registrar(texto: str) -> None:
    caminhos.preparar()
    try:
        with caminhos.REGISTRO.open("a", encoding="utf-8") as arq:
            arq.write(f"[{_agora()}] {texto}\n")
    except OSError:
        pass


def marca(ident: str) -> Path:
    return caminhos.APLICADO / ident


def aplicado(ident: str) -> bool:
    return marca(ident).is_file()


def quando(ident: str) -> str:
    try:
        return marca(ident).read_text().strip()
    except OSError:
        return ""


def marcar(ident: str) -> None:
    caminhos.preparar()
    try:
        marca(ident).write_text(_agora() + "\n")
    except OSError:
        pass


def desmarcar(ident: str) -> None:
    marca(ident).unlink(missing_ok=True)


def limpar_marcas() -> None:
    for arquivo in caminhos.APLICADO.glob("*"):
        arquivo.unlink(missing_ok=True)


def copia_de_seguranca(alvo: Path) -> bool:
    """Guarda o arquivo ou pasta antes de mexer, preservando a arvore.

    So guarda a primeira versao: o objetivo e poder voltar ao estado anterior
    ao d3bian-init-bigsur-minimalista-xfce, nao ter historico de cada execucao.
    """
    alvo = Path(alvo).expanduser()
    if not alvo.exists():
        return False
    if not caminhos.da_pessoa(alvo):
        return _copia_do_sistema(alvo)
    destino = caminhos.BACKUP / str(alvo).lstrip("/")
    if destino.exists():
        return True
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if alvo.is_dir():
            shutil.copytree(alvo, destino, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(alvo, destino)
        registrar(f"copia de seguranca: {alvo}")
        return True
    except (OSError, shutil.Error) as erro:
        registrar(f"falhou a copia de {alvo}: {erro}")
        return False


def _copia_do_sistema(alvo: Path) -> bool:
    """Arquivo do sistema: a copia fica em caminhos.BACKUP_SISTEMA, do root e
    fechada (0700), e e de la que o desfazer devolve."""
    raiz = str(caminhos.BACKUP_SISTEMA)
    destino = str(caminhos.BACKUP_SISTEMA / str(alvo).lstrip("/"))
    # so a primeira versao, como na pasta da pessoa
    trecho = ('[ -e "$2" ] || [ -L "$2" ] && exit 0; '
              'install -d -m 0700 -o root -g root "$1" && mkdir -p "$(dirname "$2")" '
              '&& cp -a "$3" "$2"')
    try:
        ok = subprocess.run(["sudo", "-n", "sh", "-c", trecho, "sh", raiz, destino, str(alvo)],
                            capture_output=True, stdin=subprocess.DEVNULL,
                            timeout=600).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    registrar(f"copia de seguranca (root): {alvo}" if ok else f"falhou a copia (root) de {alvo}")
    return ok


def restaurar_tudo() -> list[str]:
    """Devolve os arquivos guardados para o lugar. Retorna o que foi restaurado."""
    feitos: list[str] = []
    raiz = caminhos.BACKUP
    if not raiz.is_dir():
        return feitos
    for origem in sorted(raiz.rglob("*")):
        if origem.is_dir():
            continue
        relativo = origem.relative_to(raiz)
        # so volta o que veio de uma pasta que existe na raiz, como home ou etc;
        # anotacoes antigas gravadas aqui dentro (xfconf, lista de pacotes)
        # iriam parar em /xfconf
        if len(relativo.parts) < 2 or not (Path("/") / relativo.parts[0]).is_dir():
            continue
        destino = Path("/") / relativo
        # fora da casa, so o que esta na pasta do root volta (desfazer.py)
        if not caminhos.da_pessoa(destino):
            continue
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)
            feitos.append(str(destino))
        except OSError as erro:
            registrar(f"nao consegui restaurar {destino}: {erro}")
    return feitos
