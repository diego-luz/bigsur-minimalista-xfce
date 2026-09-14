"""Uma tarefa longa de cada vez, com as linhas disponiveis para a pagina web.

O que roda aqui pode ser uma funcao Python (aplicar receitas) ou um processo
externo (apt). Nos dois casos a pagina acompanha pelo mesmo endereco.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
from typing import Callable

from . import estado

_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def sem_cores(texto: str) -> str:
    return _ESCAPE.sub("", texto)


class Tarefa:
    def __init__(self) -> None:
        self._trava = threading.Lock()
        self._linhas: list[str] = []
        self.rodando = False
        self.codigo: int | None = None
        self.rotulo = ""
        self.inicio: float | None = None

    # ---- leitura ---------------------------------------------------------
    def ocupada(self) -> bool:
        with self._trava:
            return self.rodando

    def instantaneo(self, desde: int = 0) -> dict:
        with self._trava:
            return {"linhas": self._linhas[desde:], "total": len(self._linhas),
                    "rodando": self.rodando, "codigo": self.codigo,
                    "rotulo": self.rotulo,
                    # a pagina recarregada precisa do inicio para o relogio; o
                    # "agora" do servidor desconta a diferenca entre os relogios
                    "inicio": self.inicio, "agora": time.time()}

    # ---- escrita ---------------------------------------------------------
    def diz(self, texto: str) -> None:
        with self._trava:
            for linha in str(texto).splitlines() or [""]:
                self._linhas.append(sem_cores(linha))

    def _abrir(self, rotulo: str) -> bool:
        with self._trava:
            if self.rodando:
                return False
            self._linhas = []
            self.rodando = True
            self.codigo = None
            self.rotulo = rotulo
            self.inicio = time.time()
        return True

    def _fechar(self, codigo: int) -> None:
        with self._trava:
            self.codigo = codigo
            self.rodando = False

    # ---- formas de rodar -------------------------------------------------
    def funcao(self, rotulo: str, alvo: Callable[[Callable[[str], None]], int]) -> bool:
        """Roda uma funcao Python que recebe o `diz` e devolve um codigo."""
        if not self._abrir(rotulo):
            return False

        def envolver() -> None:
            try:
                codigo = int(alvo(self.diz) or 0)
            except Exception as erro:                  # a pagina precisa ver o motivo
                self.diz(f"erro inesperado: {erro}")
                estado.registrar(f"tarefa '{rotulo}' quebrou: {erro!r}")
                codigo = 1
            self._fechar(codigo)

        threading.Thread(target=envolver, daemon=True).start()
        return True

    def processo(self, rotulo: str, argumentos: list[str], root: bool = False) -> bool:
        """Roda um comando externo, repassando a saida linha a linha."""
        if root:
            argumentos = ["sudo", "-n", *argumentos]
        if not self._abrir(rotulo):
            return False

        def envolver() -> None:
            self.diz("$ " + " ".join(shlex.quote(a) for a in argumentos))
            try:
                proc = subprocess.Popen(
                    argumentos, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, text=True, bufsize=1,
                    env={**os.environ, "DEBIAN_FRONTEND": "noninteractive", "TERM": "dumb"},
                )
                assert proc.stdout is not None
                for linha in proc.stdout:
                    self.diz(linha.rstrip("\n"))
                proc.wait()
                codigo = proc.returncode
            except OSError as erro:
                self.diz(f"nao consegui executar: {erro}")
                codigo = 1
            self._fechar(codigo)

        threading.Thread(target=envolver, daemon=True).start()
        return True
