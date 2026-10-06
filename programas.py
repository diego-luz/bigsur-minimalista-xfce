"""Catalogo de programas do repositorio oficial.

O catalogo tambem e a lista de permissao: o programa so instala ou remove o
que estiver aqui. Isso importa porque quem pede e uma pagina web, e a pagina
nao deve conseguir mandar instalar qualquer coisa.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from . import caminhos, diario, hardware, motor, sistema

LIMITE = 60          # pacotes por operacao

# o que o fonte-externa.sh pode criar no sistema (chave, lista e preferencias
# de cada fonte); o desfazer com "apagar" so tira estes, e so os que nao
# existiam antes
ARQUIVOS_DE_FONTE = {
    f"{pasta}/{nome}{fim}"
    for nome in ("microsoft-vscode", "docker")
    for pasta, fim in (("/usr/share/keyrings", ".gpg"), ("/etc/apt/sources.list.d", ".list"),
                       ("/etc/apt/preferences.d", ""))
}


def catalogo() -> dict:
    try:
        return json.loads(caminhos.CATALOGO.read_text())
    except (OSError, json.JSONDecodeError):
        return {"aviso": "catalogo indisponivel", "categorias": []}


def itens() -> dict[str, dict]:
    """Todos os itens do catalogo, indexados pelo nome do pacote."""
    return {
        item["pkg"]: item
        for categoria in catalogo().get("categorias", [])
        for item in categoria.get("itens", [])
        if isinstance(item.get("pkg"), str)
    }


def fontes_necessarias(pacotes: list[str]) -> list[dict]:
    """Quais pacotes escolhidos dependem de um repositorio de terceiro."""
    tabela = itens()
    saida = []
    for nome in pacotes:
        item = tabela.get(nome, {})
        if item.get("fonte"):
            saida.append({"pkg": nome, "nome": item.get("nome", nome),
                          "fonte": item["fonte"], "aviso": item.get("aviso", "")})
    return saida


def permitidos() -> set[str]:
    return {
        item["pkg"]
        for categoria in catalogo().get("categorias", [])
        for item in categoria.get("itens", [])
        if isinstance(item.get("pkg"), str)
    }


def com_estado() -> dict:
    """O catalogo anotado com disponivel e instalado, para desenhar a pagina."""
    dados = catalogo()
    nomes = sorted(permitidos())
    estados = sistema.estado_pacotes(nomes)
    # item com "hardware" so interessa se a maquina tem aquele hardware; a
    # pagina o mostra no cartao do hardware, nao na lista comum
    maquina = hardware.detectar()
    for categoria in dados.get("categorias", []):
        for item in categoria.get("itens", []):
            item.update(estados.get(item.get("pkg", ""), {}))
            if item.get("hardware"):
                item["detectado"] = hardware.atende(item, maquina)
                usos = maquina["firmware"].get(item.get("pkg", ""))
                if usos:
                    item["motivo"] = "usado por " + ", ".join(usos)
    dados["hardware"] = maquina
    return dados


class Recusado(Exception):
    pass


def conferir(pedidos) -> list[str]:
    """Valida a lista pedida contra o catalogo. Levanta Recusado se algo nao bate."""
    if not isinstance(pedidos, list) or not pedidos:
        raise Recusado("nenhum programa informado")
    lista = permitidos()
    fora = [str(x) for x in pedidos if not isinstance(x, str) or x not in lista]
    if fora:
        raise Recusado("fora do catalogo: " + ", ".join(fora[:5]))
    if len(pedidos) > LIMITE:
        raise Recusado(f"limite de {LIMITE} programas por vez")
    # sem repetidos, mantendo a ordem
    vistos: list[str] = []
    for nome in pedidos:
        if nome not in vistos:
            vistos.append(nome)
    return vistos


def arrastaria(pacotes: list[str]) -> list[str]:
    """Simula a remocao e devolve o que o apt levaria junto sem ter sido pedido."""
    try:
        simulacao = subprocess.run(["apt-get", "-s", "remove", *pacotes],
                                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return []
    saindo = {
        linha.split()[1]
        for linha in simulacao.stdout.splitlines()
        if linha.startswith("Remv ") and len(linha.split()) > 1
    }
    return sorted(saindo - set(pacotes))


# o apt escreve o progresso em linhas "dlstatus:" e "pmstatus:" na saida; a
# pagina tira dali a barra e o pacote da vez e esconde essas linhas do log
PROGRESSO_APT = ["-o", "APT::Status-Fd=1"]


def comando_instalar(pacotes: list[str]) -> list[str]:
    # o sudo limpa o ambiente: o DEBIAN_FRONTEND vai por dentro, pelo env
    return ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", *PROGRESSO_APT,
            *motor.APT_SEM_PERGUNTAS, "install", "-y",
            "--no-install-recommends", *pacotes]


def instalar(pacotes: list[str], diz: Callable[[str], None]) -> int:
    """Habilita as fontes de terceiro, instala e roda o roteiro de cada item.

    Um item pode levar pacotes junto ("junto") e pedir um roteiro de
    configuracao depois do apt ("depois"), como o Docker rootless.
    """
    try:
        with caminhos.trava():
            return _instalar(pacotes, diz)
    except caminhos.Ocupado as erro:
        diz(f"{erro}; espere terminar")
        return 1


def remover(pacotes: list[str], diz: Callable[[str], None]) -> int:
    try:
        with caminhos.trava():
            comando = comando_remover(pacotes)
            diz("$ sudo " + " ".join(comando))
            return _correr(["sudo", "-n", *comando], diz)
    except caminhos.Ocupado as erro:
        diz(f"{erro}; espere terminar")
        return 1


def _instalar(pacotes: list[str], diz: Callable[[str], None]) -> int:
    for pedido in fontes_necessarias(pacotes):
        diz(f"habilitando a fonte de {pedido['nome']}: {pedido['fonte']}")
        roteiro = caminhos.ARQUIVOS / "fonte-externa.sh"
        antes = {c for c in ARQUIVOS_DE_FONTE if Path(c).exists()}
        codigo = _correr(["sudo", "-n", "bash", str(roteiro), pedido["fonte"]], diz)
        # anotado para o desfazer com "apagar": so o que este passo criou
        criados = sorted(c for c in ARQUIVOS_DE_FONTE - antes if Path(c).exists())
        if criados:
            diario.anotar("fonte_externa", receita="programas", fonte=pedido["fonte"],
                          criados=criados)
        if codigo != 0:
            diz("nao consegui habilitar a fonte; nada foi instalado")
            return codigo

    tabela = itens()
    todos = list(pacotes)
    for nome in pacotes:
        todos += [p for p in tabela.get(nome, {}).get("junto", []) if p not in todos]
    diz("instalando: " + ", ".join(todos))
    codigo = _correr(["sudo", "-n", *comando_instalar(todos)], diz)
    if codigo != 0:
        return codigo

    for nome in pacotes:
        roteiro = tabela.get(nome, {}).get("depois", "")
        # so nome de arquivo de recursos/arquivos, nunca um caminho
        if not roteiro or Path(roteiro).name != roteiro:
            continue
        diz(f"configurando {tabela[nome].get('nome', nome)}")
        # roda como o usuario: o que o roteiro configura e dele, e ele mesmo usa
        # sudo -n nos passos de sistema
        codigo = _correr(["bash", str(caminhos.ARQUIVOS / roteiro)], diz)
        if codigo != 0:
            return codigo
    return 0


def _correr(argumentos: list[str], diz: Callable[[str], None]) -> int:
    try:
        proc = subprocess.Popen(
            argumentos, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, bufsize=1,
            env={**os.environ, "DEBIAN_FRONTEND": "noninteractive", "TERM": "dumb"})
        assert proc.stdout is not None
        for linha in proc.stdout:
            diz(linha.rstrip("\n"))
        proc.wait()
        return proc.returncode
    except OSError as erro:
        diz(f"nao consegui executar: {erro}")
        return 1


def comando_remover(pacotes: list[str]) -> list[str]:
    return ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", *PROGRESSO_APT, "remove", "-y",
            *pacotes]
