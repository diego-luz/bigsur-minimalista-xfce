"""Catalogo de programas do repositorio oficial.

O catalogo tambem e a lista de permissao: o programa so instala ou remove o
que estiver aqui. Isso importa porque quem pede e uma pagina web, e a pagina
nao deve conseguir mandar instalar qualquer coisa.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Callable

from . import caminhos, sistema

LIMITE = 60          # pacotes por operacao


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
    for categoria in dados.get("categorias", []):
        for item in categoria.get("itens", []):
            item.update(estados.get(item.get("pkg", ""), {}))
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
    return ["apt-get", *PROGRESSO_APT, "install", "-y", "--no-install-recommends", *pacotes]


def instalar(pacotes: list[str], diz: Callable[[str], None]) -> int:
    """Habilita as fontes de terceiro que forem necessarias e instala."""
    for pedido in fontes_necessarias(pacotes):
        diz(f"habilitando a fonte de {pedido['nome']}: {pedido['fonte']}")
        roteiro = caminhos.ARQUIVOS / "fonte-externa.sh"
        codigo = _correr(["sudo", "-n", "bash", str(roteiro), pedido["fonte"]], diz)
        if codigo != 0:
            diz("nao consegui habilitar a fonte; nada foi instalado")
            return codigo

    diz("instalando: " + ", ".join(pacotes))
    return _correr(["sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive",
                    *comando_instalar(pacotes)], diz)


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
    return ["apt-get", *PROGRESSO_APT, "remove", "-y", *pacotes]
