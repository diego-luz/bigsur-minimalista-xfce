"""Os temas Xfce da familia d3bian-init nao convivem na mesma conta.

Todos usam os mesmos nomes e ajustes: os scripts d3bian-janelas,
d3bian-layouts, d3bian-bordas e d3bian-picom em ~/.local/bin, o picom.conf e o
seu autostart, o painel do xfce4, o tema e as margens do xfwm4, os atalhos de
teclado e o gtk. Instalar um segundo tema escreve por cima do primeiro, e o
"voltar" do primeiro passaria a apagar scripts que o segundo usa ou a devolver
ajustes por baixo dele. Por isso a instalacao e recusada enquanto outro tema da
familia estiver aplicado; refazer, config e restaurar do proprio tema seguem.

A troca (aplicar --trocar, ou o botao do painel) roda o restaurar do outro
tema pelo proprio projeto dele, que conhece as receitas, as listas do que pode
apagar e as copias que guardou; os pacotes dele ficam. So depois de o outro
voltar inteiro (saida 0) este tema e instalado.

O mesmo arquivo vai nos cinco projetos.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import caminhos

# pasta de estado (em ~/.local/state) -> (nome do tema, modulo python)
FAMILIA_XFCE = {
    "d3bian-init": ("bigsur-xfce", "d3bian_init_bigsur_xfce"),
    "d3bian-init-bigsur-minimalista": ("bigsur-minimalista-xfce", "d3bian_init_bigsur_minimalista_xfce"),
    "d3bian-init-minimal-xfce": ("minimal-xfce", "d3bian_init_minimal_xfce"),
    "d3bian-init-paleta-xfce": ("paleta-xfce", "d3bian_init_paleta_xfce"),
    "d3bian-init-oasis-xfce": ("oasis-xfce", "d3bian_init_oasis_xfce"),
}


def _mtime(caminho: Path) -> int:
    try:
        return caminho.stat().st_mtime_ns
    except OSError:
        return 0


def aplicado(pasta: Path) -> bool:
    """O tema desta pasta de estado mexeu na conta e nao foi desfeito.

    Conta a marca de receita aplicada em aplicado/, ou uma linha no diario
    mais nova que a pasta aplicado/: o restaurar apaga as marcas e deixa a
    pasta com a hora dele, mas guarda o diario (a remocao ainda le). So
    simulacao deixa apenas o registro.log, e isso nao conta."""
    marcas = pasta / "aplicado"
    try:
        if any(m.is_file() for m in marcas.iterdir()):
            return True
    except OSError:
        pass
    diario = pasta / "diario.jsonl"
    if _mtime(diario) <= _mtime(marcas):
        return False
    try:
        with diario.open(encoding="utf-8", errors="replace") as arquivo:
            for linha in arquivo:
                try:
                    if isinstance(json.loads(linha), dict):
                        return True
                except ValueError:
                    continue
    except OSError:
        pass
    return False


def outro_aplicado() -> tuple[str, str] | None:
    """(nome, modulo) de outro tema da familia aplicado nesta conta, ou None.
    Com este proprio tema ja aplicado nao ha o que recusar: a troca ja
    aconteceu, e refazer, config e restaurar precisam seguir."""
    proprio = caminhos.ESTADO_DIR
    if aplicado(proprio):
        return None
    for nome_pasta, (nome, modulo) in FAMILIA_XFCE.items():
        if nome_pasta != proprio.name and aplicado(proprio.parent / nome_pasta):
            return nome, modulo
    return None


def recusa() -> str:
    """A mensagem de recusa, ou vazio quando pode instalar."""
    outro = outro_aplicado()
    if not outro:
        return ""
    nome, modulo = outro
    return (f"o tema {nome} está instalado nesta conta; use o 'voltar' dele antes "
            f"(python3 -m {modulo} restaurar) ou troque de vez com "
            f"python3 -m {caminhos.PACOTE.name} aplicar --trocar")


def localizar(modulo: str) -> Path | None:
    """A pasta de onde o outro projeto roda (a que vai no PYTHONPATH).

    Primeiro a vizinha deste (os projetos lado a lado, como saem do git),
    depois o que o Python acharia sozinho (instalado no sistema). A pasta de
    estado nao guarda de onde o projeto rodou."""
    pai = caminhos.PACOTE.parent
    if (pai / modulo / "__main__.py").is_file() and (pai / modulo / "desfazer.py").is_file():
        return pai
    try:
        achado = importlib.util.find_spec(modulo)
    except (ImportError, ValueError):
        achado = None
    if achado and achado.origin:
        pasta = Path(achado.origin).parent
        if (pasta / "__main__.py").is_file() and (pasta / "desfazer.py").is_file():
            return pasta.parent
    return None


def para_pagina() -> dict | None:
    """O outro tema aplicado, para o painel oferecer a troca."""
    outro = outro_aplicado()
    if not outro:
        return None
    nome, modulo = outro
    return {"nome": nome, "modulo": modulo, "achado": localizar(modulo) is not None,
            "comando": f"python3 -m {modulo} restaurar --sim"}


def trocar(diz: Callable[[str], None], terminal: bool = False) -> int:
    """Volta o outro tema da familia pelo restaurar dele (os pacotes ficam).
    Devolve 0 quando nao ha outro ou quando ele voltou inteiro; qualquer outra
    coisa para tudo, e a conta fica como o restaurar do outro deixou."""
    outro = outro_aplicado()
    if not outro:
        return 0
    nome, modulo = outro
    pai = localizar(modulo)
    if pai is None:
        diz(f"  nao achei o projeto {modulo} para voltar o tema {nome}; rode a mao e depois "
            f"instale este de novo: python3 -m {modulo} restaurar --sim")
        return 1
    diz(f"\n==> voltando o tema {nome} ({pai / modulo})")
    comando = [sys.executable or "python3", "-m", modulo, "restaurar", "--sim"]
    ambiente = {**os.environ,
                "PYTHONPATH": str(pai) + (os.pathsep + os.environ["PYTHONPATH"]
                                          if os.environ.get("PYTHONPATH") else "")}
    try:
        if terminal:
            # no terminal a saida vai direto, e o sudo pode perguntar a senha
            codigo = subprocess.run(comando, cwd=pai, env=ambiente).returncode
        else:
            proc = subprocess.Popen(comando, cwd=pai, env=ambiente, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            assert proc.stdout is not None
            for linha in proc.stdout:
                diz(linha.rstrip("\n"))
            codigo = proc.wait()
    except OSError as erro:
        diz(f"  nao consegui rodar o restaurar do tema {nome}: {erro}")
        return 1
    if codigo != 0:
        diz(f"  o restaurar do tema {nome} terminou com erro (codigo {codigo}); parei aqui, "
            "nada deste tema foi instalado")
        return 1
    if outro_aplicado() == outro:
        diz(f"  o tema {nome} ainda aparece como instalado; parei aqui, nada deste tema foi instalado")
        return 1
    diz(f"  tema {nome} voltado; agora a instalacao deste")
    return 0
