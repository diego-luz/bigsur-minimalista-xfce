#!/usr/bin/env python3
"""Tamanho da tela, para os paineis em ilhas e o papel de parede.

    tela.py principal   x y largura altura escala, do monitor principal
    tela.py maior       largura altura, do maior monitor (em pixels de verdade)

Le o xrandr e o fator de escala do Xfce (xsettings /Gdk/WindowScalingFactor).
Sem tela (ssh, teste), vale 1920x1080. As coordenadas do painel sao em pixels
logicos: com escala 2, um monitor de 3840 tem 1920 de largura para o painel.
"""

from __future__ import annotations

import re
import subprocess
import sys

PADRAO = (0, 0, 1920, 1080)

_MONITOR = re.compile(r"^(\S+) connected( primary)?\s+(\d+)x(\d+)\+(\d+)\+(\d+)")


def _rodar(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5,
                              stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def monitores(saida: str | None = None) -> list[dict]:
    """Monitores ligados, com nome, se e o principal e a geometria."""
    if saida is None:
        saida = _rodar("xrandr", "--query")
    lista = []
    for linha in saida.splitlines():
        m = _MONITOR.match(linha)
        if m:
            lista.append({"nome": m[1], "principal": bool(m[2]), "w": int(m[3]),
                          "h": int(m[4]), "x": int(m[5]), "y": int(m[6])})
    return lista


def escala() -> int:
    valor = _rodar("xfconf-query", "-c", "xsettings", "-p", "/Gdk/WindowScalingFactor").strip()
    return int(valor) if valor.isdigit() and int(valor) > 0 else 1


def principal() -> tuple[int, int, int, int, int]:
    lista = monitores()
    mon = next((m for m in lista if m["principal"]), lista[0] if lista else None)
    x, y, w, h = (mon["x"], mon["y"], mon["w"], mon["h"]) if mon else PADRAO
    s = escala()
    return x // s, y // s, w // s, h // s, s


def maior() -> tuple[int, int]:
    lista = monitores()
    if not lista:
        return PADRAO[2], PADRAO[3]
    mon = max(lista, key=lambda m: m["w"] * m["h"])
    return mon["w"], mon["h"]


if __name__ == "__main__":
    pedido = sys.argv[1] if len(sys.argv) > 1 else "principal"
    if pedido == "maior":
        print(*maior())
    else:
        print(*principal())
