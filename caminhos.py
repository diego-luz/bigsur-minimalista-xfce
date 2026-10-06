"""Onde cada coisa mora.

Segue o padrao XDG, entao nada fica espalhado pela pasta pessoal. Os recursos
do programa (receitas, paginas, arquivos modelo) vem de dentro do proprio
pacote, o que permite rodar direto do codigo-fonte ou instalado pelo .deb, sem
mudar nada.
"""

from __future__ import annotations

import os
from pathlib import Path

PACOTE = Path(__file__).resolve().parent
RECURSOS = PACOTE / "recursos"
RECEITAS = RECURSOS / "receitas"
WEB = RECURSOS / "web"
ARQUIVOS = RECURSOS / "arquivos"
CATALOGO = RECURSOS / "programas.json"


def _xdg(variavel: str, padrao: str) -> Path:
    bruto = os.environ.get(variavel, "").strip()
    base = Path(bruto) if bruto.startswith("/") else Path.home() / padrao
    return base


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "d3bian-init-bigsur-minimalista"
ESTADO_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "d3bian-init-bigsur-minimalista"
DADOS_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "d3bian-init-bigsur-minimalista"
# versoes anteriores dividiam a pasta de dados com o d3bian-init-bigsur-xfce;
# so o desfazer de uma instalacao antiga ainda olha para ela
DADOS_DIR_ANTIGO = _xdg("XDG_DATA_HOME", ".local/share") / "d3bian-init"

CONFIG = CONFIG_DIR / "config.json"
REGISTRO = ESTADO_DIR / "registro.log"
APLICADO = ESTADO_DIR / "aplicado"
BACKUP = ESTADO_DIR / "backup"
FONTES = DADOS_DIR / "fontes"          # repositorios clonados
CAPTURAS = DADOS_DIR / "capturas"      # previas feitas pelo usuario

# Copias do que e do sistema (/etc, /usr/share) ficam numa pasta do root: o
# desfazer devolve como root, e uma copia numa pasta da pessoa poderia ser
# trocada por qualquer programa dela antes de voltar para o sistema.
BACKUP_SISTEMA = Path("/var/backups/d3bian-init-bigsur-minimalista-xfce")


def preparar() -> None:
    """Cria as pastas de trabalho. Barato, pode chamar sempre."""
    for pasta in (CONFIG_DIR, ESTADO_DIR, APLICADO, BACKUP, DADOS_DIR, FONTES, CAPTURAS):
        pasta.mkdir(parents=True, exist_ok=True)
    # log e copias de seguranca podem ter caminhos e variaveis da pessoa: so ela le
    for pasta in (ESTADO_DIR, BACKUP):
        os.chmod(pasta, 0o700)


def da_pessoa(caminho: Path) -> bool:
    """Dentro da pasta pessoal: o que o proprio usuario pode mexer sem sudo."""
    return Path(caminho).is_relative_to(Path.home())


def proteger_codigo() -> None:
    """Tira a escrita de grupo e de outros do proprio codigo. Parte dele roda
    com sudo; um arquivo que outra conta pudesse mudar viraria um atalho para
    o root. So mexe no que e da pessoa."""
    uid = os.getuid()
    for raiz, pastas, arquivos in os.walk(PACOTE):
        for nome in [*pastas, *arquivos]:
            caminho = os.path.join(raiz, nome)
            try:
                info = os.lstat(caminho)
            except OSError:
                continue
            if info.st_uid == uid and info.st_mode & 0o022 and not os.path.islink(caminho):
                os.chmod(caminho, info.st_mode & ~0o022)


def escrever(destino: Path, texto: str, modo: int | None = None) -> None:
    """Grava inteiro ou nada: um corte no meio (queda de energia, Ctrl+C) nao
    deixa o arquivo pela metade. Mantem a permissao do arquivo que existia.

    Link simbolico (um arquivo que aponta para um repositorio de dotfiles) e
    seguido: grava no arquivo de verdade e o link continua link. Arquivo com
    mais de um nome (link fisico) ou de outro dono e regravado no lugar, para
    nao separar os nomes nem trocar o dono."""
    import tempfile
    destino = Path(destino)
    if destino.is_symlink():
        destino = Path(os.path.realpath(destino))
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        info = destino.stat()
    except OSError:
        info = None
    if info is not None and (info.st_nlink > 1 or info.st_uid != os.getuid()):
        with open(destino, "r+") as arquivo:
            arquivo.write(texto)
            arquivo.truncate()
            arquivo.flush()
            os.fsync(arquivo.fileno())
        if modo is not None:
            os.chmod(destino, modo)
        return
    if modo is None:
        if info is not None:
            modo = info.st_mode & 0o7777
        else:
            mascara = os.umask(0)
            os.umask(mascara)
            modo = 0o666 & ~mascara
    fd, temp = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.")
    try:
        with os.fdopen(fd, "w") as arquivo:
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.chmod(temp, modo)
        os.replace(temp, destino)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


class Ocupado(RuntimeError):
    """Outra execucao (o painel ou a linha de comando) ja esta mexendo."""


def livre() -> bool:
    """A trava esta livre agora? (para nao gravar opcoes de uma execucao que
    seria recusada porque a linha de comando ja esta rodando)"""
    try:
        with trava():
            return True
    except Ocupado:
        return False


class trava:
    """Uma execucao por vez entre processos: o painel e a linha de comando
    rodando juntos brigariam pelo apt e pelos mesmos arquivos."""

    def __enter__(self):
        import fcntl
        preparar()
        self._arquivo = open(ESTADO_DIR / "trava", "w")
        try:
            fcntl.flock(self._arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._arquivo.close()
            raise Ocupado("outra execucao deste projeto ja esta rodando") from None
        return self

    def __exit__(self, *_a) -> None:
        self._arquivo.close()


def captura(nome: str) -> Path:
    """Uma previa: a do usuario tem prioridade sobre a que vem no pacote."""
    propria = CAPTURAS / f"{nome}.jpg"
    return propria if propria.is_file() else WEB / "capturas" / f"{nome}.jpg"
