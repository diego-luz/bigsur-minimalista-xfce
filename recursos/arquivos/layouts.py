#!/usr/bin/env python3
"""Seletor de layouts de janela, como o do Windows 11 (Super+Z).

Abre um quadro com desenhos de layouts em cima da janela ativa; clicar numa
das partes de um desenho leva a janela para aquela parte da tela. O xfwm4 nao
deixa por nada no botao de maximizar, entao o quadro abre pelo atalho.

    d3bian-layouts          abre o quadro para a janela ativa
    Esc ou clicar fora      fecha sem mexer em nada
"""

from __future__ import annotations

import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

# cada layout e uma lista de partes: x, y, largura, altura, em fracao da tela
LAYOUTS = [
    [(0, 0, 1 / 2, 1), (1 / 2, 0, 1 / 2, 1)],
    [(0, 0, 2 / 3, 1), (2 / 3, 0, 1 / 3, 1)],
    [(0, 0, 1 / 3, 1), (1 / 3, 0, 1 / 3, 1), (2 / 3, 0, 1 / 3, 1)],
    [(0, 0, 1 / 2, 1), (1 / 2, 0, 1 / 2, 1 / 2), (1 / 2, 1 / 2, 1 / 2, 1 / 2)],
    [(0, 0, 1 / 2, 1 / 2), (1 / 2, 0, 1 / 2, 1 / 2),
     (0, 1 / 2, 1 / 2, 1 / 2), (1 / 2, 1 / 2, 1 / 2, 1 / 2)],
    [(0, 0, 1 / 4, 1), (1 / 4, 0, 1 / 2, 1), (3 / 4, 0, 1 / 4, 1)],
]
CENTRO = (0.14, 0.11, 0.72, 0.78)
CARTAO_L, CARTAO_A, VAO = 104, 64, 4


def x11(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def numeros(saida: str) -> list[int]:
    valores = saida.partition("=")[2].replace(",", " ").split()
    try:
        return [int(v, 0) for v in valores]
    except ValueError:
        return []


def janela_ativa() -> int | None:
    ids = numeros(x11("xprop", "-root", "-notype", "_NET_ACTIVE_WINDOW"))
    if not ids or ids[0] == 0:
        return None
    tipo = x11("xprop", "-id", str(ids[0]), "-notype", "_NET_WM_WINDOW_TYPE")
    if "DESKTOP" in tipo or "DOCK" in tipo:
        return None
    return ids[0]


def geometria(janela: int) -> tuple[int, int, int, int] | None:
    saida = x11("xwininfo", "-id", str(janela))
    campos = {}
    for linha in saida.splitlines():
        chave, _, valor = linha.strip().partition(":")
        campos[chave] = valor.strip()
    try:
        return (int(campos["Absolute upper-left X"]), int(campos["Absolute upper-left Y"]),
                int(campos["Width"]), int(campos["Height"]))
    except (KeyError, ValueError):
        return None


def margens_xfwm4() -> tuple[int, int, int, int]:
    """Margens do xfwm4 (esquerda, direita, cima, baixo), em pixels de verdade.

    Painel solto da borda (as ilhas) nao reserva espaco e fica fora da area
    util que o GDK le (_NET_WORKAREA); quem guarda o lugar dele sao as margens.
    """
    valores = []
    for lado in ("left", "right", "top", "bottom"):
        texto = x11("xfconf-query", "-c", "xfwm4", "-p", f"/general/margin_{lado}").strip()
        valores.append(int(texto) if texto.isdigit() else 0)
    return valores[0], valores[1], valores[2], valores[3]


def area_util(monitor) -> tuple[int, int, int, int]:
    """A area util do monitor menos as margens do xfwm4, em pixels logicos (GDK)."""
    escala = monitor.get_scale_factor()
    r, g = monitor.get_workarea(), monitor.get_geometry()
    # o GDK fala em pixels logicos; as margens vem em pixels de verdade
    esq, dir_, cima, baixo = (-(-m // escala) for m in margens_xfwm4())
    x1, y1 = max(r.x, g.x + esq), max(r.y, g.y + cima)
    x2 = min(r.x + r.width, g.x + g.width - dir_)
    y2 = min(r.y + r.height, g.y + g.height - baixo)
    if x2 - x1 < 200 or y2 - y1 < 150:
        return r.x, r.y, r.width, r.height
    return x1, y1, x2 - x1, y2 - y1


def mover(janela: int, area: tuple[int, int, int, int], parte) -> None:
    ax, ay, aw, ah = area
    fx, fy, fw, fh = parte
    x, y = ax + round(aw * fx), ay + round(ah * fy)
    w, h = round(aw * fw), round(ah * fh)
    alvo = f"0x{janela:08x}"
    x11("wmctrl", "-i", "-r", alvo, "-b", "remove,maximized_vert,maximized_horz,fullscreen")
    # wmctrl mede o conteudo; a moldura do tema sai da conta
    esq, dir_, cima, baixo = (numeros(x11("xprop", "-id", str(janela), "-notype",
                                          "_NET_FRAME_EXTENTS")) + [0, 0, 0, 0])[:4]
    w, h = max(w - esq - dir_, 200), max(h - cima - baixo, 150)
    x11("wmctrl", "-i", "-r", alvo, "-e", f"0,{x},{y},{w},{h}")
    x11("wmctrl", "-i", "-a", alvo)


def maximizar(janela: int) -> None:
    alvo = f"0x{janela:08x}"
    x11("wmctrl", "-i", "-r", alvo, "-b", "add,maximized_vert,maximized_horz")
    x11("wmctrl", "-i", "-a", alvo)


class Cartao(Gtk.DrawingArea):
    """O desenho de um layout; a parte sob o mouse fica na cor de destaque."""

    def __init__(self, partes, escolher) -> None:
        super().__init__()
        self.partes = partes
        self.escolher = escolher
        self.sob = -1
        self.set_size_request(CARTAO_L, CARTAO_A)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("draw", self.desenhar)
        self.connect("motion-notify-event", self.mexeu)
        self.connect("leave-notify-event", lambda *_: self.marcar(-1))
        self.connect("button-release-event", self.clicou)

    def retangulos(self):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        for fx, fy, fw, fh in self.partes:
            yield (fx * w + VAO / 2, fy * h + VAO / 2, fw * w - VAO, fh * h - VAO)

    def parte_em(self, x: float, y: float) -> int:
        for i, (rx, ry, rw, rh) in enumerate(self.retangulos()):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return i
        return -1

    def marcar(self, indice: int) -> None:
        if indice != self.sob:
            self.sob = indice
            self.queue_draw()

    def mexeu(self, _w, evento) -> None:
        self.marcar(self.parte_em(evento.x, evento.y))

    def clicou(self, _w, evento) -> None:
        i = self.parte_em(evento.x, evento.y)
        if i >= 0:
            self.escolher(self.partes[i])

    def desenhar(self, _w, cr) -> None:
        estilo = self.get_style_context()
        achou, destaque = estilo.lookup_color("theme_selected_bg_color")
        texto = estilo.get_color(Gtk.StateFlags.NORMAL)
        for i, (x, y, w, h) in enumerate(self.retangulos()):
            raio = 5
            cr.new_sub_path()
            cr.arc(x + w - raio, y + raio, raio, -1.5708, 0)
            cr.arc(x + w - raio, y + h - raio, raio, 0, 1.5708)
            cr.arc(x + raio, y + h - raio, raio, 1.5708, 3.1416)
            cr.arc(x + raio, y + raio, raio, 3.1416, 4.7124)
            cr.close_path()
            if i == self.sob and achou:
                cr.set_source_rgba(destaque.red, destaque.green, destaque.blue, 1)
                cr.fill()
            else:
                cr.set_source_rgba(texto.red, texto.green, texto.blue, 0.10)
                cr.fill_preserve()
                cr.set_source_rgba(texto.red, texto.green, texto.blue, 0.35)
                cr.set_line_width(1)
                cr.stroke()


class Quadro(Gtk.Window):
    def __init__(self, janela: int) -> None:
        super().__init__(title="Layouts")
        self.janela = janela
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.get_style_context().add_class("background")

        geo = geometria(janela)
        tela = Gdk.Display.get_default()
        if geo:
            monitor = tela.get_monitor_at_point(geo[0] + geo[2] // 2, geo[1] + geo[3] // 2)
        else:
            monitor = tela.get_primary_monitor() or tela.get_monitor(0)
        escala = monitor.get_scale_factor()
        lx, ly, lw, lh = area_util(monitor)
        # o wmctrl fala em pixels de verdade; o quadro (GTK), em logicos
        self.area = (lx * escala, ly * escala, lw * escala, lh * escala)
        self.limite = (lx, ly, lw, lh)
        self.geo = geo
        self.escolhido = False

        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        caixa.set_border_width(12)
        grade = Gtk.Grid(column_spacing=10, row_spacing=10)
        for i, partes in enumerate(LAYOUTS):
            grade.attach(Cartao(partes, self.escolher), i % 3, i // 3, 1, 1)
        caixa.pack_start(grade, False, False, 0)

        botoes = Gtk.Box(spacing=6, homogeneous=True)
        for rotulo, acao in (("Maximizar", self.maximizar), ("Centralizar", self.centralizar)):
            b = Gtk.Button(label=rotulo)
            b.connect("clicked", lambda _b, a=acao: a())
            botoes.pack_start(b, True, True, 0)
        caixa.pack_start(botoes, False, False, 0)
        self.add(caixa)

        self.connect("key-press-event", self.tecla)
        self.connect("focus-out-event", lambda *_: self.fechar())
        self.connect("realize", self.posicionar)

    def posicionar(self, *_args) -> None:
        # como no Windows, logo abaixo da barra de titulo, no meio da janela
        largura, altura = self.get_preferred_size()[1].width, self.get_preferred_size()[1].height
        lx, ly, lw, lh = self.limite
        if self.geo:
            escala = self.get_scale_factor()
            gx, gy, gw, _ = (v // escala for v in self.geo)
            x, y = gx + (gw - largura) // 2, gy + 8
        else:
            x, y = lx + (lw - largura) // 2, ly + (lh - altura) // 3
        x = min(max(x, lx + 8), lx + lw - largura - 8)
        y = min(max(y, ly + 8), ly + lh - altura - 8)
        self.move(x, y)

    def tecla(self, _w, evento) -> bool:
        if evento.keyval == Gdk.KEY_Escape:
            self.fechar()
            return True
        return False

    def fechar(self) -> None:
        if self.escolhido:
            return
        self.hide()
        Gtk.main_quit()

    def depois(self, acao) -> None:
        # o quadro some antes, para o foco voltar para a janela certa
        self.escolhido = True
        self.hide()
        GLib.timeout_add(60, lambda: (acao(), Gtk.main_quit()) and False)

    def escolher(self, parte) -> None:
        self.depois(lambda: mover(self.janela, self.area, parte))

    def centralizar(self) -> None:
        self.depois(lambda: mover(self.janela, self.area, CENTRO))

    def maximizar(self) -> None:
        self.depois(lambda: maximizar(self.janela))


def main(args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    janela = janela_ativa()
    if janela is None:
        return 0
    quadro = Quadro(janela)
    quadro.show_all()
    quadro.present()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
