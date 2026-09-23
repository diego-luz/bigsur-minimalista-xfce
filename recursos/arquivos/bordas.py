#!/usr/bin/env python3
"""Copia o tema do xfwm4 com bordas mais largas, para agarrar e redimensionar.

Os temas que usamos (WhiteSur, Orchis, Nordic, Gruvbox, Everforest) desenham
a borda lateral e a de baixo com 1 ou 2 pixels, e so da para redimensionar
acertando esse fio. O xfwm4 so aceita clique em pixel 100% opaco, entao uma
borda invisivel nao funciona: a borda nova precisa ser pintada. Ela e pintada
com a cor da barra de titulo, entre o contorno do tema e o conteudo, e a janela
parece so ter uma moldura um pouco mais cheia.

    d3bian-bordas                 usa o tema atual do xfwm4
    d3bian-bordas TEMA [PIXELS]   o padrao e 4 pixels a mais

Cria ~/.themes/TEMA-bordas/xfwm4 e escreve o nome dele na saida. Quem chama
decide se aplica (xfconf-query -c xfwm4 -p /general/theme -s NOME).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib  # noqa: E402

SUFIXO = "-bordas"
# ordem em que o xfwm4 procura o que vai por cima do xpm
IMAGENS = ("svg", "png", "gif", "jpg", "bmp")
CHARS = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
         "0123456789#$%&*+-=@;:,<>?!~^_|/()[]{}")


def pasta_do_tema(nome: str) -> Path | None:
    dados = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    bases = [Path.home() / ".themes", Path.home() / ".local/share/themes"]
    bases += [Path(d) / "themes" for d in dados if d]
    for base in bases:
        if (base / nome / "xfwm4" / "themerc").is_file():
            return base / nome / "xfwm4"
    return None


# --------------------------------------------------------------------------
# imagem como grade de valores: tupla RGBA (png) ou definicao de cor (xpm)
# --------------------------------------------------------------------------

class Grade:
    def __init__(self, linhas: list[list], opaco) -> None:
        self.linhas = linhas
        self.opaco = opaco

    @property
    def w(self) -> int:
        return len(self.linhas[0]) if self.linhas else 0

    @property
    def h(self) -> int:
        return len(self.linhas)

    def px(self, x: int, y: int):
        return self.linhas[y][x]

    def inserir_colunas(self, onde: int, n: int, valor) -> None:
        for y, linha in enumerate(self.linhas):
            linha[onde:onde] = [valor(y)] * n

    def inserir_linhas(self, onde: int, n: int, valor) -> None:
        novas = [[valor(x) for x in range(self.w)] for _ in range(n)]
        self.linhas[onde:onde] = novas


def ler_pixbuf(caminho: Path) -> Grade:
    pb = GdkPixbuf.Pixbuf.new_from_file(str(caminho))
    if not pb.get_has_alpha():
        pb = pb.add_alpha(False, 0, 0, 0)
    w, h, passo = pb.get_width(), pb.get_height(), pb.get_rowstride()
    dados = pb.get_pixels()
    linhas = [[tuple(dados[y * passo + x * 4:y * passo + x * 4 + 4]) for x in range(w)]
              for y in range(h)]
    return Grade(linhas, lambda v: v[3] == 255)


def gravar_png(grade: Grade, caminho: Path) -> None:
    bruto = bytes(b for linha in grade.linhas for px in linha for b in px)
    pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bruto), GdkPixbuf.Colorspace.RGB,
                                         True, 8, grade.w, grade.h, grade.w * 4)
    pb.savev(str(caminho), "png", [], [])


def _normal(definicao: str) -> str:
    return " ".join(definicao.split())


def ler_xpm(caminho: Path) -> tuple[Grade, str]:
    texto = caminho.read_text(errors="replace")
    textos = re.findall(r'"((?:[^"\\]|\\.)*)"', texto)
    w, h, n, cpp = (int(x) for x in textos[0].split()[:4])
    cores = {}
    for linha in textos[1:1 + n]:
        cores[linha[:cpp]] = _normal(linha[cpp:])
    linhas = []
    for linha in textos[1 + n:1 + n + h]:
        linhas.append([cores[linha[i:i + cpp]] for i in range(0, w * cpp, cpp)])
    nome = re.search(r"char\s*\*\s*(\w+)", texto)
    return Grade(linhas, lambda v: "none" not in v.lower().split()), (nome.group(1) if nome else "xpm")


def gravar_xpm(grade: Grade, caminho: Path, nome: str) -> None:
    usadas = list(dict.fromkeys(v for linha in grade.linhas for v in linha))
    cpp = 1 if len(usadas) <= len(CHARS) else 2
    chaves = [CHARS[i] if cpp == 1 else CHARS[i // len(CHARS)] + CHARS[i % len(CHARS)]
              for i in range(len(usadas))]
    mapa = dict(zip(usadas, chaves))
    saida = ["/* XPM */", f"static char *{nome}[] = {{",
             f'"{grade.w} {grade.h} {len(usadas)} {cpp} ",']
    saida += [f'"{mapa[v]} {v}",' for v in usadas]
    saida += ['"' + "".join(mapa[v] for v in linha) + '",' for linha in grade.linhas]
    saida[-1] = saida[-1].rstrip(",")
    saida.append("};")
    caminho.write_text("\n".join(saida) + "\n")


# --------------------------------------------------------------------------
# alargar
# --------------------------------------------------------------------------

def carregar(origem: Path, peca: str) -> dict[str, tuple[Grade, str]]:
    """Todas as imagens de uma peca, por formato: xpm e o que for por cima."""
    achadas: dict[str, tuple[Grade, str]] = {}
    xpm = origem / f"{peca}.xpm"
    if xpm.is_file():
        achadas["xpm"] = ler_xpm(xpm)
    for ext in IMAGENS:
        arquivo = origem / f"{peca}.{ext}"
        if arquivo.is_file():
            try:
                achadas[ext] = (ler_pixbuf(arquivo), "")
            except GLib.Error:
                continue
            break
    return achadas


def cor_do_titulo(origem: Path, estado: str) -> dict[str, object]:
    """A cor do meio da barra de titulo, em cada formato."""
    cores: dict[str, object] = {}
    for peca in (f"title-3-{estado}", f"title-1-{estado}", f"top-left-{estado}"):
        for ext, (grade, _) in carregar(origem, peca).items():
            x = grade.w // 2 if peca.startswith("title") else grade.w - 1
            valor = grade.px(x, grade.h // 2)
            if grade.opaco(valor):
                cores.setdefault("xpm" if ext == "xpm" else "img", valor)
        if len(cores) == 2:
            break
    if "img" in cores and "xpm" not in cores:
        r, g, b, _ = cores["img"]
        cores["xpm"] = f"c #{r:02X}{g:02X}{b:02X}"
    if "xpm" in cores and "img" not in cores:
        cor = re.search(r"#([0-9A-Fa-f]{6})", str(cores["xpm"]))
        rgb = bytes.fromhex(cor.group(1)) if cor else b"\x80\x80\x80"
        cores["img"] = (*rgb, 255)
    return cores


def alargar(grade: Grade, peca: str, n: int, fundo, contorno: set) -> None:
    lado, _, _ = peca.rpartition("-")
    esquerda = lado != "bottom-right"

    # o pixel novo copia o vizinho de dentro quando ele e contorno ou fica fora
    # da curva do canto; no resto vira a cor da barra de titulo. Transparente
    # com borda do lado de fora e a parte que ficava atras da janela, e essa
    # agora aparece
    def regra(x: int, y: int):
        ref = grade.px(x, y)
        if grade.opaco(ref):
            return ref if ref in contorno else fundo
        fora = range(x) if esquerda else range(x + 1, grade.w)
        return fundo if any(grade.opaco(grade.px(i, y)) for i in fora) else ref

    if lado in ("left", "bottom-left"):
        ref = min(1, grade.w - 1)
        col = [fundo if lado == "left" else regra(ref, y) for y in range(grade.h)]
        grade.inserir_colunas(1, n, lambda y: col[y])
    if lado in ("right", "bottom-right"):
        ref = max(grade.w - 2, 0)
        col = [fundo if lado == "right" else regra(ref, y) for y in range(grade.h)]
        grade.inserir_colunas(grade.w - 1, n, lambda y: col[y])
    if lado in ("bottom", "bottom-left", "bottom-right"):
        ref = max(grade.h - 2, 0)
        lin = [fundo if lado == "bottom" else regra(x, ref) for x in range(grade.w)]
        grade.inserir_linhas(grade.h - 1, n, lambda x: lin[x])


def contornos(origem: Path, estado: str) -> dict[str, set]:
    """O pixel de fora das bordas lateral e de baixo, em cada formato."""
    saida: dict[str, set] = {"xpm": set(), "img": set()}
    for peca, onde in ((f"left-{estado}", lambda g: (0, g.h // 2)),
                       (f"right-{estado}", lambda g: (g.w - 1, g.h // 2)),
                       (f"bottom-{estado}", lambda g: (g.w // 2, g.h - 1))):
        for ext, (grade, _) in carregar(origem, peca).items():
            saida["xpm" if ext == "xpm" else "img"].add(grade.px(*onde(grade)))
    return saida


PECAS = ("left", "right", "bottom", "bottom-left", "bottom-right")


def gerar(tema: str, n: int) -> str:
    base = tema[:-len(SUFIXO)] if tema.endswith(SUFIXO) else tema
    origem = pasta_do_tema(base)
    if origem is None:
        raise SystemExit(f"nao achei o tema {base} do xfwm4")
    nome = base + SUFIXO
    destino = Path.home() / ".themes" / nome / "xfwm4"
    if destino.parent.exists():
        shutil.rmtree(destino.parent)
    shutil.copytree(origem, destino, symlinks=False)

    for estado in ("active", "inactive"):
        fundo = cor_do_titulo(origem, estado)
        if not fundo:
            continue
        linhas = contornos(origem, estado)
        for lado in PECAS:
            peca = f"{lado}-{estado}"
            for ext, (grade, rotulo) in carregar(origem, peca).items():
                chave = "xpm" if ext == "xpm" else "img"
                alargar(grade, peca, n, fundo[chave], linhas[chave])
                if ext == "xpm":
                    gravar_xpm(grade, destino / f"{peca}.xpm", rotulo)
                else:
                    # svg, gif e afins viram png, que o xfwm4 le igual
                    for outro in IMAGENS:
                        (destino / f"{peca}.{outro}").unlink(missing_ok=True)
                    gravar_png(grade, destino / f"{peca}.png")
    return nome


def tema_atual() -> str:
    try:
        return subprocess.run(["xfconf-query", "-c", "xfwm4", "-p", "/general/theme"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit("nao consegui ler o tema atual do xfwm4")


def main(args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    tema = args[0] if args else tema_atual()
    n = int(args[1]) if len(args) > 1 else 4
    if not 1 <= n <= 12:
        raise SystemExit("use de 1 a 12 pixels")
    print(gerar(tema, n))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
