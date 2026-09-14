"""Fotos da tela, usadas como previa na pagina.

As que vem no pacote sao exemplos genericos, feitos por
ferramentas/gerar_exemplos.py numa sessao separada; valem ate o usuario
fotografar a propria tela.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from . import caminhos, config, motor

LARGURA = 1280


def nome_do_momento(cfg: dict[str, str] | None = None) -> str:
    """Qual previa corresponde as preferencias que estao valendo agora."""
    cfg = cfg or config.ler()
    tema = "escuro" if cfg.get("tema") == "escuro" else "claro"
    widget = "com" if cfg.get("widget") == "sim" else "sem"
    return f"{tema}-{widget}-widget"


def _redimensionar(origem: Path, destino: Path) -> bool:
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        pronto = subprocess.run(
            ["convert", str(origem), "-resize", f"{LARGURA}x", "-quality", "86",
             str(destino)], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pronto = False
    if not pronto:                      # sem ImageMagick, guarda o png cru
        try:
            destino.with_suffix(".png").write_bytes(origem.read_bytes())
            return True
        except OSError:
            return False
    return True


def tirar(nome: str, diz: Callable[[str], None]) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        bruto = Path(tmp.name)
    try:
        ok = subprocess.run(["xfce4-screenshooter", "-f", "-s", str(bruto)],
                            capture_output=True, timeout=60).returncode == 0
        if not ok or bruto.stat().st_size == 0:
            diz("  nao consegui fotografar a tela")
            return False
        destino = caminhos.CAPTURAS / f"{nome}.jpg"
        if _redimensionar(bruto, destino):
            diz(f"  previa salva: {nome}")
            return True
        diz("  nao consegui gravar a previa")
        return False
    except (OSError, subprocess.TimeoutExpired) as erro:
        diz(f"  falhou a captura: {erro}")
        return False
    finally:
        bruto.unlink(missing_ok=True)


def contar(segundos: int, diz: Callable[[str], None]) -> None:
    if segundos > 0:
        diz(f"  fotografando em {segundos}s, deixe a tela como quer mostrar")
        time.sleep(segundos)


def capturar_atual(diz: Callable[[str], None], espera: int = 5) -> int:
    contar(espera, diz)
    return 0 if tirar(nome_do_momento(), diz) else 1


def capturar_todas(diz: Callable[[str], None], espera: int = 5) -> int:
    """Percorre as quatro combinacoes e devolve o estado original no fim."""
    from . import receitas                      # import tardio, evita ciclo

    original = config.ler()
    contar(espera, diz)
    falhas = 0
    for tema in ("escuro", "claro"):
        for widget in ("sim", "nao"):
            diz(f"  preparando: tema {tema}, widget {widget}")
            cfg = {**original, "tema": tema, "widget": widget}
            receitas.executar(apenas=["38", "40", "80"], refazer=True,
                              saida=lambda _t: None, cfg=cfg)
            time.sleep(4)
            if not tirar(f"{tema}-{'com' if widget == 'sim' else 'sem'}-widget", diz):
                falhas += 1
    diz("  devolvendo o estado anterior")
    receitas.executar(apenas=["38", "40", "80"], refazer=True,
                      saida=lambda _t: None, cfg=original)
    return 1 if falhas else 0


def _tela() -> tuple[int, int]:
    """Largura e altura da tela inteira."""
    try:
        linha = subprocess.run(["xrandr", "--current"], capture_output=True,
                               text=True, timeout=10).stdout.splitlines()[0]
        partes = linha.split("current", 1)[1].split(",")[0].split("x")
        largura, altura = int(partes[0]), int(partes[1])
        if largura > 0 and altura > 0:
            return largura, altura
    except (OSError, subprocess.TimeoutExpired, IndexError, ValueError):
        pass
    return 1920, 1200


def _tamanho_da_tela() -> str:
    """O formato do monitor, reduzido para caber numa janela."""
    largura, altura = _tela()
    return f"{LARGURA}x{round(altura * LARGURA / largura)}"


def previa_login(diz: Callable[[str], None], cfg: dict[str, str] | None = None,
                 destino: Path | None = None) -> int:
    """Monta a tela de login com as opcoes pedidas e a fotografa numa janela.

    Usa o modo de teste do LightDM, que roda sem root um daemon separado e
    le a configuracao na hora. O `dm-tool add-nested-seat` nao serve: quem
    cria o seat e o daemon ja em execucao, que mostra o greeter antigo.
    """
    import os
    import shutil
    from . import receitas                      # import tardio, evita ciclo

    lightdm = shutil.which("lightdm") or "/usr/sbin/lightdm"
    faltam = [nome for nome, ok in (
        ("xserver-xephyr", shutil.which("Xephyr")),
        ("lightdm", Path(lightdm).is_file()),
        ("lightdm-gtk-greeter", Path("/usr/sbin/lightdm-gtk-greeter").is_file()),
        ("imagemagick", shutil.which("convert")),
    ) if not ok]
    if faltam:
        diz("  para a previa falta instalar: " + ", ".join(faltam))
        return 1

    receita = receitas.por_id().get("97")
    if receita is None:
        diz("  nao achei a receita da tela de login")
        return 1
    # pasta temporaria, apagada no fim; so a foto fica, junto das outras previas
    pasta = Path(tempfile.mkdtemp(prefix="d3bian-init-previa-login-"))
    try:
        return _previa_login(diz, {**config.ler(), **(cfg or {})}, receita, pasta, lightdm,
                             destino or caminhos.CAPTURAS / "login.jpg")
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def _previa_login(diz: Callable[[str], None], cfg: dict[str, str], receita,
                  pasta: Path, lightdm: str, destino: Path) -> int:
    import os
    import shutil

    # os mesmos passos da instalacao, montados na pasta da previa e sem ir ao sistema
    ctx = motor.montar_contexto(cfg)
    ctx.update(login_dir=str(pasta), login_raiz=str(pasta), login_instalar="nao")
    try:
        motor.Motor(ctx, saida=diz).rodar(receita.passos)
    except motor.ErroDePasso as erro:
        diz(f"  nao consegui montar a previa: {erro}")
        return 1
    for sub in ("run", "log", "cache", "bin"):
        (pasta / sub).mkdir(parents=True, exist_ok=True)

    # o greeter procura a configuracao e o tema nas pastas XDG do sistema
    envelope = pasta / "greeter.sh"
    envelope.write_text(
        "#!/bin/sh\n"
        f"export XDG_CONFIG_DIRS='{pasta}/xdg'\n"
        f"export XDG_DATA_DIRS='{pasta}/share:/usr/local/share:/usr/share'\n"
        'exec "$@"\n')
    envelope.chmod(0o755)
    # no modo de teste o LightDM chama o Xephyr pelo PATH, sem opcao de tamanho
    xephyr = pasta / "bin" / "Xephyr"
    xephyr.write_text("#!/bin/sh\n"
                      f"exec {shutil.which('Xephyr')} -screen {_tamanho_da_tela()} \"$@\"\n")
    xephyr.chmod(0o755)
    ajustes = pasta / "lightdm.conf"
    ajustes.write_text(
        "[Seat:*]\n"
        "greeter-session=lightdm-gtk-greeter\n"
        f"greeter-wrapper={envelope}\n"
        f"greeter-hide-users={ctx['login_esconder_usuarios']}\n"
        "greeter-show-manual-login=true\n")

    diz("  abrindo a tela de login em uma janela")
    try:
        daemon = subprocess.Popen(
            [lightdm, "--test-mode", "-c", str(ajustes), f"--run-dir={pasta}/run",
             f"--log-dir={pasta}/log", f"--cache-dir={pasta}/cache"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            env={**os.environ, "PATH": f"{pasta}/bin:{os.environ.get('PATH', '')}"})
    except OSError as erro:
        diz(f"  nao consegui iniciar o lightdm em modo de teste: {erro}")
        return 1

    try:
        tela, autorizacao = "", ""
        for _ in range(30):
            time.sleep(1)
            if daemon.poll() is not None:
                break
            try:
                listagem = subprocess.run(["pgrep", "-a", "Xephyr"], capture_output=True,
                                          text=True, timeout=10).stdout
            except (OSError, subprocess.TimeoutExpired):
                listagem = ""
            # so o Xephyr desta previa, reconhecido pela pasta de autorizacao
            for linha in listagem.splitlines():
                if str(pasta) in linha:
                    partes = linha.split()
                    tela = next((p for p in partes if p.startswith(":") and p[1:].isdigit()), "")
                    # o Xephyr do modo de teste exige o cookie que o LightDM
                    # gravou; sem ele, o import so conecta por sorte do ambiente
                    if "-auth" in partes and partes.index("-auth") + 1 < len(partes):
                        autorizacao = partes[partes.index("-auth") + 1]
            if tela and (pasta / "log" / "seat0-greeter.log").exists():
                break
        if not tela:
            diz("  a tela de login nao abriu; ultimas linhas do registro do lightdm:")
            try:
                for linha in (pasta / "log" / "lightdm.log").read_text().splitlines()[-8:]:
                    diz("    " + linha)
            except OSError:
                pass
            return 1
        time.sleep(5)                    # o greeter carrega o tema e o fundo
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            bruto = Path(tmp.name)
        try:
            ambiente = {**os.environ, "DISPLAY": tela}
            if autorizacao:
                ambiente["XAUTHORITY"] = autorizacao
            subprocess.run(["import", "-window", "root", str(bruto)],
                           env=ambiente, capture_output=True, timeout=40)
            if bruto.stat().st_size and _redimensionar(bruto, destino):
                diz("  previa da tela de login salva")
            else:
                diz("  a janela abriu, mas nao consegui fotografar")
                return 1
        except (OSError, subprocess.TimeoutExpired):
            diz("  a janela abriu, mas nao consegui fotografar")
            return 1
        finally:
            bruto.unlink(missing_ok=True)
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=15)
        except subprocess.TimeoutExpired:
            daemon.kill()
    diz("  esta e a tela com as opcoes marcadas; a de verdade muda ao aplicar e reiniciar")
    return 0


# usado pelo servidor para montar o contexto sem reimportar motor
montar_contexto = motor.montar_contexto
