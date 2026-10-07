#!/usr/bin/env python3
"""Monta o perfil da barra em ilhas (vindo do d3bian-init-oasis-xfce).

    paineis.py --perfil ARQUIVO.tar.bz2 [opcoes]   escreve o perfil
    paineis.py --perfil ARQUIVO --listar [opcoes]  so mostra o que o load escreveria

O perfil e o mesmo .tar.bz2 do xfce4-panel-profiles (config.txt com as
propriedades em texto GVariant e os .rc dos plugins), e quem aplica e o
"xfce4-panel-profiles load": ele passa pelo xfconfd, que guarda o canal em
memoria.

Ilhas: uma barra fina solta no topo (menu, bandeja, som, energia, relogio e
sair), com cantos redondos, e as janelas abertas numa ilha no meio, embaixo,
tambem solta da borda. Sem lista de janelas (tarefas = nenhuma), fica so a
barra de cima.

O painel do Xfce so solta da borda na posicao livre (p=0), em que x e y sao o
centro do painel. Por isso a ilha de baixo cresce com o dock (length-adjust) e
fica sempre no centro. Painel solto nao reserva espaco na tela: a saida traz as
margens que o xfwm4 precisa guardar ("margens CIMA BAIXO") para as janelas
maximizadas nao passarem por baixo das ilhas. O painel mede em pixels logicos e
as margens do xfwm4 sao em pixels de verdade: com a escala 2 do Xfce, elas
saem dobradas.

Os favoritos do docklike (docklike-N.rc) vao dentro do perfil; o load copia
para ~/.config/xfce4/panel. Plugin que nao esta instalado fica de fora: um id
sem .desktop abre a janela "o plugin nao pode ser carregado".
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tela  # noqa: E402

# medidas em pixels logicos
BARRA_ALTURA = 30          # barra de cima
BARRA_VAO = 6              # vao entre a barra de cima e a borda
ILHA_ALTURA = 48           # ilha das janelas, embaixo
ILHA_VAO = 10              # vao entre a ilha e a borda
ILHA_ICONE = 32


class Montador:
    def __init__(self, args: argparse.Namespace) -> None:
        self.a = args
        self.proximo = 0
        self.props: dict[str, str] = {}
        # caminho relativo a ~/.config/xfce4/panel -> conteudo
        self.arquivos: dict[str, str] = {}
        self.usados: list[str] = []
        self.avisos: list[str] = []

    # ---- utilidades ------------------------------------------------------
    def tem(self, plugin: str) -> bool:
        return (Path(self.a.plugins_dir) / f"{plugin}.desktop").is_file()

    def plugin(self, nome: str, props: dict[str, tuple[str, object]] | None = None) -> int:
        """Acrescenta o plugin e devolve o id. props: nome -> (tipo, valor)."""
        self.proximo += 1
        pid = self.proximo
        self.usados.append(nome)
        self.props[f"/plugins/plugin-{pid}"] = gvariant("string", nome)
        for chave, (tipo, valor) in (props or {}).items():
            self.props[f"/plugins/plugin-{pid}/{chave}"] = gvariant(tipo, valor)
        return pid

    def separador(self, expande: bool) -> int:
        """Expandido empurra o resto para a direita; fixo e a folga nas pontas,
        longe do canto redondo (o plugin que roda fora do painel pinta um
        retangulo por cima dele)."""
        return self.plugin("separator", {"expand": ("bool", expande), "style": ("uint", 0)})

    def menu(self) -> int | None:
        if self.a.menu == "nenhum":
            return None
        if not self.tem("whiskermenu"):
            self.avisos.append("atencao: o menu Whisker nao esta instalado; a barra fica sem ele")
            return None
        props: dict[str, tuple[str, object]] = {
            "button-icon": ("string", self.a.menu_icone),
            "show-button-icon": ("bool", True),
            "show-button-title": ("bool", self.a.menu == "icone_texto"),
            "launcher-show-description": ("bool", False),
            "load-hierarchy": ("bool", True),
        }
        # NOME:TIPO:VALOR, o que cada projeto pede a mais no menu
        for extra in self.a.menu_extra:
            nome, tipo, valor = extra.split(":", 2)
            props[nome] = (tipo, valor == "true" if tipo == "bool" else valor)
        return self.plugin("whiskermenu", props)

    def tarefas(self) -> int | None:
        if self.a.tarefas == "nenhuma":
            return None
        if self.a.tarefas == "docklike":
            nome = next((p for p in ("docklike", "xfce4-docklike-plugin") if self.tem(p)), "")
            if nome:
                pid = self.plugin(nome)
                favoritos = [f for f in self.a.favoritos.split(";") if f and self._app_existe(f)]
                # firefox-esr e firefox sao o mesmo programa; fica so o primeiro
                if "firefox-esr" in favoritos and "firefox" in favoritos:
                    favoritos.remove("firefox")
                rc = ["[user]", "pinned=" + "".join(f"{f};" for f in favoritos),
                      "indicatorColorFromTheme=false",
                      f"indicatorColor={self.a.destaque}",
                      "noWindowsListIfSingle=true",
                      "forceIconSize=true",
                      f"iconSize={ILHA_ICONE}"]
                self.arquivos[f"{nome}-{pid}.rc"] = "\n".join(rc) + "\n"
                return pid
            self.avisos.append("atencao: o docklike nao esta instalado; usando os botoes de janela")
        return self.plugin("tasklist", {"grouping": ("bool", True), "show-labels": ("bool", False),
                                        "show-handle": ("bool", False)})

    def _app_existe(self, ident: str) -> bool:
        return any((Path(d) / f"{ident}.desktop").is_file() for d in self.a.apps_dirs.split(":") if d)

    def bandeja(self) -> list[int]:
        ids = []
        if self.tem("systray"):
            ids.append(self.plugin("systray", {"square-icons": ("bool", True),
                                               "symbolic-icons": ("bool", True)}))
        for p in ("notification-plugin", "pulseaudio", "power-manager-plugin"):
            if self.tem(p):
                ids.append(self.plugin(p))
        # layout 3 e so o campo de hora; o formato ja traz data e hora juntas
        ids.append(self.plugin("clock", {
            "mode": ("uint", 2),
            "digital-layout": ("uint", 3),
            "digital-time-format": ("string", self.a.relogio),
            "digital-format": ("string", self.a.relogio),
            "tooltip-format": ("string", "%A, %d de %B de %Y"),
        }))
        ids.append(self.plugin("actions", {"appearance": ("uint", 1),
                                           "ask-confirmation": ("bool", True)}))
        return ids

    # ---- paineis ---------------------------------------------------------
    def painel(self, numero: int, posicao: str, comprimento: float, ajusta: bool,
               altura: int, icone: int, fundo: str, ids: list[int]) -> None:
        r, g, b, alfa = (float(v) for v in fundo.split())
        base = f"/panels/panel-{numero}"
        for chave, tipo, valor in (
            ("position", "string", posicao),
            ("position-locked", "bool", True),
            ("length", "double", comprimento),
            ("length-adjust", "bool", ajusta),
            ("size", "uint", altura),
            ("icon-size", "uint", icone),
            ("nrows", "uint", 1),
            ("mode", "uint", 0),
            ("background-style", "uint", 1),
            ("background-rgba", "array-double", [r, g, b, alfa]),
            ("enter-opacity", "uint", 100),
            ("leave-opacity", "uint", 100),
            ("autohide-behavior", "uint", 0),
            ("plugin-ids", "array-int", ids),
        ):
            self.props[f"{base}/{chave}"] = gvariant(tipo, valor)

    def ilhas(self) -> tuple[int, tuple[int, int]]:
        x, y, w, h = self.a.tela[:4]

        # barra de cima, solta da borda pelo vao
        ids = [self.separador(False)] + [i for i in (self.menu(),) if i]
        ids.append(self.separador(True))
        ids += self.bandeja()
        ids.append(self.separador(False))
        largura = w - 2 * BARRA_VAO
        self.painel(
            1, f"p=0;x={x + w // 2};y={y + BARRA_VAO + BARRA_ALTURA // 2}",
            largura * 100 / w, False, BARRA_ALTURA, 16, self.a.fundo_barra, ids)

        dock = self.tarefas()
        if dock is None:
            return 1, (BARRA_ALTURA + 2 * BARRA_VAO, 0)

        # ilha de baixo: cresce com os programas abertos, sempre no centro
        ids = [self.separador(False), dock, self.separador(False)]
        self.painel(
            2, f"p=0;x={x + w // 2};y={y + h - ILHA_VAO - ILHA_ALTURA // 2}",
            1.0, True, ILHA_ALTURA, ILHA_ICONE, self.a.fundo_ilha, ids)
        return 2, (BARRA_ALTURA + 2 * BARRA_VAO, ILHA_ALTURA + 2 * ILHA_VAO)

    def config(self) -> tuple[str, tuple[int, int]]:
        """O config.txt do perfil: uma propriedade por linha, CAMINHO VALOR."""
        paineis, margens = self.ilhas()
        self.props["/configver"] = gvariant("int", 2)
        self.props["/panels"] = gvariant("array-int", list(range(1, paineis + 1)))
        self.props["/panels/dark-mode"] = gvariant("bool", self.a.modo == "escuro")
        linhas = [f"{chave} {valor}" for chave, valor in sorted(self.props.items())]
        return "\n".join(linhas) + "\n", margens


def gvariant(tipo: str, valor: object) -> str:
    """O valor no texto do GVariant, como o xfce4-panel-profiles grava e le
    (GLib.Variant.parse). Lista do xfconf e um array de variantes: [<1>, <2>]."""
    if tipo == "string":
        texto = str(valor).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{texto}'"
    if tipo == "bool":
        return "true" if valor else "false"
    if tipo == "int":
        return str(int(valor))
    if tipo == "uint":
        return f"uint32 {int(valor)}"
    if tipo == "double":
        # sempre com ponto, senao o parse le como inteiro
        return repr(float(valor))
    if tipo.startswith("array-"):
        item = tipo.split("-", 1)[1]
        return "[" + ", ".join(f"<{gvariant(item, v)}>" for v in valor) + "]"
    raise ValueError(f"tipo desconhecido: {tipo}")


def _no_tar(t: tarfile.TarFile, nome: str, conteudo: str) -> None:
    dados = conteudo.encode("utf-8")
    info = tarfile.TarInfo(name=nome)
    info.size = len(dados)
    info.mtime = int(time.time())
    info.mode = 0o644
    t.addfile(info, io.BytesIO(dados))


def gravar_perfil(destino: Path, config: str, arquivos: dict[str, str]) -> None:
    """Inteiro ou nada: escreve ao lado e troca de uma vez."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.")
    os.close(fd)
    try:
        with tarfile.open(tmp, "w:bz2") as t:
            _no_tar(t, "config.txt", config)
            for nome, conteudo in sorted(arquivos.items()):
                _no_tar(t, nome, conteudo)
        os.chmod(tmp, 0o644)
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    casa = Path.home()
    dados = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    config = Path(os.environ.get("XDG_CONFIG_HOME") or casa / ".config")
    p = argparse.ArgumentParser(description="Monta o perfil da barra do Xfce em ilhas.")
    p.add_argument("--perfil", required=True, help="o .tar.bz2 que o xfce4-panel-profiles load aplica")
    p.add_argument("--listar", action="store_true",
                   help="so mostra o que o load escreveria em ~/.config/xfce4/panel")
    p.add_argument("--config-dir", default=str(config / "xfce4/panel"))
    p.add_argument("--plugins-dir", default="/usr/share/xfce4/panel/plugins")
    p.add_argument("--apps-dirs", default=":".join(
        [str(casa / ".local/share/applications")] + [f"{d}/applications" for d in dados if d]))
    p.add_argument("--tela", help="x y largura altura (pixels logicos); sem ela, le o xrandr")
    p.add_argument("--escala", type=int, help="fator de escala do Xfce; sem ele, le o xsettings")
    p.add_argument("--modo", choices=["escuro", "claro"], default="escuro")
    p.add_argument("--menu", choices=["icone", "icone_texto", "nenhum"], default="icone")
    p.add_argument("--menu-icone", default="view-app-grid-symbolic")
    p.add_argument("--menu-extra", action="append", default=[],
                   help="propriedade a mais do menu Whisker, NOME:TIPO:VALOR")
    p.add_argument("--tarefas", choices=["docklike", "botoes", "nenhuma"], default="docklike")
    p.add_argument("--favoritos", default="thunar;xfce4-terminal")
    p.add_argument("--relogio", default="%a %d %b  %H:%M")
    p.add_argument("--fundo-ilha", default="0.08 0.09 0.10 0.82")
    p.add_argument("--fundo-barra", default="0.08 0.09 0.10 0.78")
    p.add_argument("--destaque", default="#1a73e8")
    a = p.parse_args(argv)
    if a.tela:
        a.tela = tuple(int(v) for v in a.tela.split())
        a.escala = a.escala or 1
    else:
        *a.tela, escala = tela.principal()
        a.escala = a.escala or escala
    return a


def main(argv: list[str] | None = None) -> int:
    a = argumentos(argv)
    m = Montador(a)
    texto, (cima, baixo) = m.config()
    if a.listar:
        pasta = Path(a.config_dir)
        for nome in sorted({n.split("/", 1)[0] for n in m.arquivos}):
            print(pasta / nome)
        return 0
    for aviso in m.avisos:
        print(aviso)
    gravar_perfil(Path(a.perfil), texto, m.arquivos)
    print("plugins: " + " ".join(m.usados))
    # as margens do xfwm4 sao em pixels de verdade, e o painel em pixels logicos
    s = max(a.escala, 1)
    print(f"margens {cima * s} {baixo * s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
