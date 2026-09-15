"""Deteccao do ambiente e verificacoes previas.

Tudo que e especifico de ambiente grafico fica aqui. Hoje so o XFCE esta
implementado, mas quem chama pergunta pela capacidade, nao pelo nome do
desktop, entao acrescentar outro depois nao obriga a mexer nas receitas.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path


def _roda(*argumentos: str, tempo: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(argumentos, capture_output=True, text=True, timeout=tempo)


def tem(programa: str) -> bool:
    return shutil.which(programa) is not None


def distribuicao() -> dict[str, str]:
    dados: dict[str, str] = {}
    try:
        for linha in Path("/etc/os-release").read_text().splitlines():
            if "=" in linha:
                chave, _, valor = linha.partition("=")
                dados[chave.strip()] = valor.strip().strip('"')
    except OSError:
        pass
    return dados


def desktop() -> str:
    return os.environ.get("XDG_CURRENT_DESKTOP", "").strip()


def e_xfce() -> bool:
    return "XFCE" in desktop().upper() or tem("xfconf-query")


def sessao_grafica() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def sudo_liberado() -> bool:
    """Ha credencial em cache, ou seja, da para usar sudo sem perguntar nada."""
    try:
        return _roda("sudo", "-n", "true", tempo=6).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def pacote_instalado(nome: str) -> bool:
    try:
        saida = _roda("dpkg-query", "-W", "-f=${db:Status-Status}", nome, tempo=8).stdout
        return saida.strip() == "installed"
    except (OSError, subprocess.TimeoutExpired):
        return False


def estado_pacotes(nomes: list[str]) -> dict[str, dict]:
    """Para cada pacote: se o repositorio oferece e se ja esta instalado."""
    fora = {n: {"disponivel": False, "instalado": False, "versao": ""} for n in nomes}
    if not nomes:
        return fora
    try:
        saida = _roda("dpkg-query", "-W", "-f=${binary:Package} ${db:Status-Status}\n",
                      *nomes, tempo=20).stdout
        for linha in saida.splitlines():
            partes = linha.split()
            if len(partes) == 2 and partes[1] == "installed":
                nome = partes[0].split(":")[0]
                if nome in fora:
                    fora[nome]["instalado"] = True
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        saida = _roda("apt-cache", "policy", *nomes, tempo=30).stdout
        atual = None
        for linha in saida.splitlines():
            if linha and not linha.startswith(" ") and linha.rstrip().endswith(":"):
                atual = linha.rstrip()[:-1].split(":")[0]
            elif atual in fora and ":" in linha:
                rotulo, _, valor = linha.strip().partition(":")
                # o apt e traduzido; "Candidat" cobre Candidate e Candidato
                if rotulo.startswith("Candidat"):
                    valor = valor.strip()
                    if valor and valor not in ("(none)", "(nenhum)"):
                        fora[atual]["disponivel"] = True
                        fora[atual]["versao"] = valor
    except (OSError, subprocess.TimeoutExpired):
        pass
    return fora


def espaco_livre_gb(onde: Path | None = None) -> float:
    try:
        st = os.statvfs(str(onde or Path.home()))
        return st.f_bavail * st.f_frsize / 1e9
    except OSError:
        return -1.0


def _repositorios_do_apt() -> list[str]:
    """Enderecos http(s) das fontes do apt, os do Debian primeiro."""
    pasta = Path("/etc/apt/sources.list.d")
    arquivos = [Path("/etc/apt/sources.list"), *sorted(pasta.glob("*.list")),
                *sorted(pasta.glob("*.sources"))]
    enderecos: list[str] = []
    for arquivo in arquivos:
        try:
            texto = arquivo.read_text()
        except OSError:
            continue
        for linha in texto.splitlines():
            linha = linha.split("#", 1)[0].strip()
            if linha.startswith("URIs:"):
                enderecos += linha[5:].split()
            elif linha.startswith(("deb ", "deb-src ")):
                enderecos += [p for p in linha.split() if "://" in p][:1]
    vistos: dict[str, str] = {}
    for url in enderecos:
        host = url.split("://", 1)[-1].split("/", 1)[0]
        if url.startswith(("http://", "https://")) and host not in vistos:
            vistos[host] = url
    return sorted(vistos.values(), key=lambda u: "debian" not in u)


def _proxy_do_apt() -> dict[str, str]:
    """O proxy que o apt usa, quando ha; a rede pode so sair por ele."""
    try:
        saida = _roda("apt-config", "shell", "HTTP", "Acquire::http::Proxy",
                      "HTTPS", "Acquire::https::Proxy", tempo=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    proxies: dict[str, str] = {}
    for linha in saida.splitlines():
        nome, _, valor = linha.partition("=")
        valor = shlex.split(valor)[0] if valor.strip() else ""
        if valor and valor.upper() != "DIRECT":
            proxies[nome.lower()] = valor
    return proxies


def repositorios_alcancaveis() -> tuple[bool, str]:
    """Pergunta aos repositorios do apt se respondem.

    Nao usa curl: ele nao vem numa instalacao padrao do Debian e so chega com a
    receita 10, depois desta verificacao. Qualquer resposta HTTP, ate um 404,
    ja prova que o servidor foi alcancado.
    """
    import urllib.error
    import urllib.request
    urls = _repositorios_do_apt()[:2] or ["http://deb.debian.org/debian/"]
    proxies = {**urllib.request.getproxies(), **_proxy_do_apt()}
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    hosts = []
    for url in urls:
        host = url.split("://", 1)[-1].split("/", 1)[0]
        hosts.append(host)
        try:
            abridor.open(urllib.request.Request(url, method="HEAD"), timeout=6).close()
            return True, host
        except urllib.error.HTTPError:
            return True, host
        except (OSError, ValueError):
            continue
    return False, ", ".join(hosts)


_CACHE: tuple[float, list[dict]] | None = None
VALIDADE = 30.0          # segundos


def verificacoes(usar_cache: bool = True) -> list[dict]:
    """Lista de checagens previas, no formato que a pagina web desenha.

    Guarda o resultado por meio minuto: a faixa de estado do topo consulta em
    toda pagina, e uma delas fala com a rede.
    """
    global _CACHE
    import time
    if usar_cache and _CACHE and (time.monotonic() - _CACHE[0]) < VALIDADE:
        return _CACHE[1]
    lista = _verificar()
    _CACHE = (time.monotonic(), lista)
    return lista


def _verificar() -> list[dict]:
    saida: list[dict] = []

    def add(nome: str, ok: bool, detalhe: str, critico: bool = True) -> None:
        saida.append({"nome": nome, "ok": bool(ok), "detalhe": detalhe, "critico": critico})

    info = distribuicao()
    nome_distro = info.get("PRETTY_NAME", "") or "nao identificado"
    familia = (info.get("ID", "") + " " + info.get("ID_LIKE", "")).lower()
    add("Sistema", "debian" in familia, nome_distro)

    add("Ambiente grafico", e_xfce(), desktop() or "desconhecido")
    add("Sessao grafica", sessao_grafica(),
        "ativa" if sessao_grafica() else "sem DISPLAY; rode dentro da sua sessao")
    add("xfconf-query", tem("xfconf-query"),
        "presente" if tem("xfconf-query") else "faltando, vem com o xfconf")

    liberado = sudo_liberado()
    add("Permissao de administrador", liberado,
        "autorizada nesta sessao" if liberado
        else "sem credencial; abra o painel pelo comando d3bian-init-bigsur")

    gb = espaco_livre_gb()
    add("Espaco em disco", gb < 0 or gb >= 2.0,
        "nao verificado" if gb < 0 else f"{gb:.1f} GB livres na pasta pessoal",
        critico=gb >= 0)

    rede, hosts = repositorios_alcancaveis()
    add("Acesso aos repositorios", rede,
        f"alcancaveis ({hosts})" if rede else f"sem resposta de {hosts}")

    return saida


def impedimentos(lista: list[dict] | None = None) -> list[str]:
    """Nomes das verificacoes criticas que falharam."""
    return [c["nome"] for c in (lista or verificacoes()) if c["critico"] and not c["ok"]]
