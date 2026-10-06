#!/usr/bin/env python3
"""Gera as imagens de exemplo da pagina: a previa do desktop e a do tema.

Nao roda na maquina de quem usa o painel: e ferramenta de quem mantem o
projeto, e as imagens vao prontas em recursos/web.

Cada imagem e uma *simulacao* desenhada em HTML e fotografada pelo chromium:
papel de parede, a barra unica do topo e uma janela, com as cores aproximadas do
WhiteSur solido. Nao e foto do Xfce rodando; quem quiser a de verdade usa o
botao "Capturar a tela como esta" na propria pagina, que troca estas.

Nada da maquina de quem gera entra aqui: a pasta e sempre "Imagens", o relogio
e uma hora fixa e nao ha nome de usuario nenhum.

    python3 ferramentas/gerar_exemplos.py

Precisa de chromium e ImageMagick.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAPTURAS = RAIZ / "recursos/web/capturas"
EXEMPLOS = RAIZ / "recursos/web/exemplos"

HORA = "seg 15 set  14:20"
PASTAS = ["Documentos", "Imagens", "Downloads", "Projetos", "Musica", "Videos"]

# tema -> janela, barra de titulo, texto, lateral, destaque, borda, barra do topo,
#         texto da barra, papel de parede (as duas pontas do degrade)
CORES = {
    "escuro": ("#2c2c2e", "#262628", "#f2f2f7", "#1e1e20", "#0860f2", "#3a3a3c",
               "rgba(28,28,33,.96)", "#f2f2f7", ("#3a2b63", "#8e3b5e")),
    "claro": ("#fbfbfd", "#f2f2f5", "#1d1d1f", "#f0f0f2", "#0860f2", "#d8d8dc",
              "rgba(247,247,252,.96)", "#1d1d1f", ("#9ab7e8", "#dfc6d8")),
}

PAGINA = """<!doctype html><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:1280px;height:800px;overflow:hidden;background:{papel_b}}}
body{{font:13px/1.4 "DejaVu Sans",system-ui,sans-serif}}
.area{{position:absolute;inset:0;background:linear-gradient(160deg,{papel_a},{papel_b})}}
.barra{{position:absolute;left:0;right:0;top:0;height:30px;display:flex;align-items:center;
  gap:12px;padding:0 14px;background:{barra};color:{barra_texto};font-size:12.5px}}
.barra .menu{{width:13px;height:13px;border-radius:50%;background:{barra_texto};opacity:.9}}
.barra .esp{{flex:1}}
.barra .dir{{display:flex;gap:11px;align-items:center;opacity:.9}}
.barra .dir i{{width:11px;height:11px;border-radius:3px;background:{barra_texto};opacity:.5}}
.jan{{position:absolute;left:250px;top:120px;width:780px;height:470px;border-radius:11px;
  overflow:hidden;background:{janela};color:{texto};border:1px solid {borda};
  box-shadow:0 26px 60px rgba(0,0,0,.42)}}
.tit{{height:38px;display:flex;align-items:center;padding:0 14px;background:{titulo};
  border-bottom:1px solid {borda};font-size:13px;font-weight:600;position:relative}}
.tit span{{position:absolute;left:0;right:0;text-align:center;opacity:.9}}
.tit .bts{{margin-left:auto;display:flex;gap:9px;z-index:1}}
.tit .bts i{{width:12px;height:12px;border-radius:50%;display:block}}
.corpo{{display:flex;height:calc(100% - 38px)}}
.lado{{width:190px;background:{lateral};border-right:1px solid {borda};padding:12px 10px;
  display:flex;flex-direction:column;gap:3px}}
.lado a{{display:flex;align-items:center;gap:9px;padding:7px 9px;border-radius:8px;
  font-size:12.5px;opacity:.85}}
.lado a.on{{background:{destaque};color:#fff;opacity:1;font-weight:600}}
.lado a b{{width:14px;height:12px;border-radius:3px;background:{destaque};opacity:.75;display:block}}
.lado a.on b{{background:#fff}}
.grade{{flex:1;padding:18px;display:grid;grid-template-columns:repeat(4,1fr);gap:18px;align-content:start}}
.grade div{{text-align:center;font-size:12px;opacity:.85}}
.grade div b{{display:block;height:58px;border-radius:9px;background:{destaque};opacity:.2;margin-bottom:7px}}
</style>
<div class="area">
  <div class="barra">
    <span class="menu"></span>
    <div class="esp"></div>
    <div class="dir"><i></i><i></i><i></i><span>{hora}</span></div>
  </div>
  <div class="jan">
    <div class="tit"><span>Imagens</span>
      <div class="bts"><i style="background:#febc2e"></i><i style="background:#28c840"></i>
        <i style="background:#ff5f57"></i></div></div>
    <div class="corpo">
      <div class="lado">{lado}</div>
      <div class="grade">{grade}</div>
    </div>
  </div>
</div>"""


def cena(tema: str) -> str:
    janela, titulo, texto, lateral, destaque, borda, barra, barra_texto, papel = CORES[tema]
    lado = "".join(f'<a class="{"on" if i == 0 else ""}"><b></b>{p}</a>'
                   for i, p in enumerate(["Inicio"] + PASTAS[:4]))
    grade = "".join(f"<div><b></b>{p}</div>" for p in PASTAS)
    return PAGINA.format(janela=janela, titulo=titulo, texto=texto, lateral=lateral,
                         destaque=destaque, borda=borda, barra=barra, barra_texto=barra_texto,
                         papel_a=papel[0], papel_b=papel[1], hora=HORA, lado=lado, grade=grade)


def fotografar(pagina: str, destinos: list[tuple[Path, int]]) -> None:
    """Uma renderizacao so; cada destino sai na largura que a pagina usa."""
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "cena.html"
        arq.write_text(pagina)
        png = Path(tmp) / "cena.png"
        subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
                        "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1280,800", f"--screenshot={png}", f"file://{arq}"],
                       capture_output=True, timeout=120, check=True)
        for destino, largura in destinos:
            destino.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["convert", str(png), "-resize", f"{largura}x", "-quality", "86",
                            "-strip", str(destino)], check=True)
            print(f"  {destino.relative_to(RAIZ)}  {destino.stat().st_size // 1024} KB")


def main() -> int:
    for tema in ("escuro", "claro"):
        print(f"{tema}:")
        fotografar(cena(tema), [(CAPTURAS / f"{tema}.jpg", 1280),
                                (EXEMPLOS / f"tema-{tema}.jpg", 640)])
    # as do bigsur completo mostram dock e widget, que aqui nao existem
    for velha in CAPTURAS.glob("*-widget.jpg"):
        velha.unlink()
        print(f"  apagada a antiga {velha.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
