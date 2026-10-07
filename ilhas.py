"""Barra em ilhas e efeitos com o picom, vindos do d3bian-init-oasis-xfce.

O que as receitas 38 (painel) e 46 (efeitos) interpolam: as cores das ilhas,
que seguem o tema e a cor de destaque, e o picom.conf, que depende do video
desta maquina (sem aceleracao, o picom roda leve, sem desfoque).
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

# a cor de destaque do WhiteSur, a mesma da previa da pagina
DESTAQUES = {"padrao": "#0860f2", "azul": "#2e7cf7", "roxo": "#9a57a3", "rosa": "#e55e9c",
             "vermelho": "#ed5f5d", "laranja": "#e9873a", "amarelo": "#f3ba4b",
             "verde": "#79b757", "cinza": "#8c8c8c"}

# raio dos cantos das ilhas; o picom usa o mesmo, para o desfoque nao vazar
RAIO = 14

# programas fixados no dock da ilha de baixo, na ordem; so entram os que existem
FAVORITOS = ["thunar", "xfce4-terminal", "firefox-esr", "firefox", "org.xfce.mousepad"]


def maquina_virtual() -> bool:
    """Todo hipervisor liga a marca `hypervisor` no processador."""
    try:
        return " hypervisor" in Path("/proc/cpuinfo").read_text()
    except OSError:
        return False


def exec_desktop(*argumentos: str) -> str:
    """A linha Exec de um .desktop, com as aspas da especificacao: a pasta
    pessoal pode ter espaco ("/home/joao silva") ou %."""
    def um(arg: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_./:=+,@-]+", arg):
            arg = '"' + re.sub(r'([\\"`$])', r"\\\1", arg) + '"'
        return arg.replace("%", "%%")

    # o valor do .desktop tem os escapes do proprio arquivo: \ vira \\
    return " ".join(um(a) for a in argumentos).replace("\\", "\\\\")


# video sem aceleracao: o picom com glx e desfoque fica lento, ou as janelas
# param de redesenhar (o caso classico e a VM sem 3D)
_SOFTWARE = ("llvmpipe", "softpipe", "swrast", "software rasterizer")
# drivers de video que nao tem 3D (o virtio_gpu pode ter, com virgl, e fica de fora)
_VIDEO_SEM_3D = {"qxl", "bochs", "bochs-drm", "cirrus", "cirrus-qemu", "vboxvideo",
                 "simpledrm", "efifb", "vesafb", "hyperv_drm", "hyperv_fb"}


@functools.lru_cache(maxsize=4)
def _render_software(glxinfo: str, display: str, virtual: bool) -> tuple[bool, str]:
    if os.environ.get("LIBGL_ALWAYS_SOFTWARE") in ("1", "true"):
        return True, "LIBGL_ALWAYS_SOFTWARE ligado"
    if glxinfo and display:
        try:
            saida = subprocess.run([glxinfo, "-B"], capture_output=True, text=True, timeout=6,
                                   stdin=subprocess.DEVNULL,
                                   env={**os.environ, "LC_ALL": "C"}).stdout.lower()
        except (OSError, subprocess.TimeoutExpired):
            saida = ""
        if "direct rendering: no" in saida:
            return True, "sem renderizacao direta (glxinfo)"
        for linha in saida.splitlines():
            if "opengl renderer string" in linha:
                if any(s in linha for s in _SOFTWARE):
                    return True, "video desenhado pelo processador (" + linha.split(":", 1)[1].strip() + ")"
                return False, ""
    drivers = set()
    for card in Path("/sys/class/drm").glob("card[0-9]"):
        try:
            drivers.add(os.path.basename(os.readlink(card / "device/driver")))
        except OSError:
            pass
    if drivers and drivers <= _VIDEO_SEM_3D:
        return True, "placa de video sem 3D (" + ", ".join(sorted(drivers)) + ")"
    if virtual:
        return True, "maquina virtual sem confirmacao de aceleracao 3D"
    return False, ""


def render_software() -> tuple[bool, str]:
    """(sim ou nao, motivo). O glxinfo (mesa-utils) chega com a receita 10."""
    return _render_software(shutil.which("glxinfo") or "", os.environ.get("DISPLAY", ""),
                            maquina_virtual())


def _picom(cfg: dict[str, str]) -> dict[str, str]:
    efeitos = cfg.get("efeitos", "desligado")
    # so pergunta ao video quando o picom vai rodar
    software, motivo = render_software() if efeitos != "desligado" else (False, "")
    desfoque = efeitos == "desfoque" and not software
    if efeitos == "desligado":
        aviso = "efeitos desligados: vale o compositor do proprio Xfce"
    elif software:
        aviso = f"picom em modo leve (xrender, sem desfoque nem vsync): {motivo}"
    elif desfoque:
        aviso = "picom com desfoque, sombras e cantos arredondados"
    else:
        aviso = "picom com sombras e cantos arredondados, sem desfoque"
    linhas_desfoque = "\n".join([
        'blur-method = "dual_kawase";',
        "blur-strength = 5;",
        "blur-background = true;",
        "blur-background-frame = false;",
        "blur-background-fixed = false;",
        "blur-background-exclude = [",
        '  "window_type = \'desktop\'",',
        '  "window_type = \'dnd\'",',
        '  "window_type = \'tooltip\'",',
        '  "_GTK_FRAME_EXTENTS@",',
        '  "class_g = \'firefox\' && argb",',
        '  "class_g = \'firefox-esr\' && argb",',
        '  "class_g = \'Firefox-esr\' && argb"',
        "];",
    ]) if desfoque else "# sem desfoque (pela opcao ou pelo video desta maquina)"
    # janelas translucidas so com desfoque; sem ele o texto de tras atrapalha
    linhas_opacidade = "\n".join([
        "opacity-rule = [",
        '  "94:class_g = \'Xfce4-terminal\' && focused",',
        '  "88:class_g = \'Xfce4-terminal\' && !focused"',
        "];",
    ]) if desfoque else "# janelas opacas: a transparencia so vale junto com o desfoque"
    # a barra colada na borda fica reta; as ilhas sao arredondadas
    excluir_barra = "" if cfg.get("ilhas") == "sim" else '  "window_type = \'dock\'",'
    return {
        "picom_backend": "xrender" if software else "glx",
        "picom_vsync": "false" if software else "true",
        "picom_desfoque": linhas_desfoque,
        "picom_opacidade": linhas_opacidade,
        "picom_excluir_barra": excluir_barra,
        "picom_aviso": aviso,
        # o autostart chama o d3bian-picom, que religa o xfwm4 se o picom cair
        "picom_exec": exec_desktop(str(Path.home() / ".local/bin/d3bian-picom")),
    }


def contexto(cfg: dict[str, str]) -> dict[str, str]:
    escuro = cfg.get("tema") == "escuro"
    destaque = DESTAQUES.get(cfg.get("destaque", "padrao"), DESTAQUES["padrao"])
    dr, dg, db = (int(destaque[i:i + 2], 16) for i in (1, 3, 5))
    ctx = {
        "raio": str(RAIO),
        # o mesmo tom da barra unica, um pouco translucido
        "ilha_fundo_barra": "0.11 0.11 0.13 0.82" if escuro else "0.97 0.97 0.99 0.82",
        "ilha_fundo": "0.11 0.11 0.13 0.86" if escuro else "0.97 0.97 0.99 0.86",
        "painel_hover": "rgba(255, 255, 255, 0.10)" if escuro else "rgba(0, 0, 0, 0.07)",
        "destaque_cor": destaque,
        "destaque_suave": f"rgba({dr}, {dg}, {db}, 0.22)",
        "favoritos": ";".join(FAVORITOS),
    }
    ctx.update(_picom(cfg))
    return ctx
