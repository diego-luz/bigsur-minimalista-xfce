"""Carrega as receitas e executa as que forem pedidas.

Uma receita e um arquivo TOML em recursos/receitas. Ela se descreve: numero de
ordem, titulo, de quais outras depende e quais preferencias a afetam. Esse
ultimo campo e o que permite a pagina web decidir sozinha o que reexecutar
quando o usuario muda uma opcao, sem nenhuma tabela em codigo.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import caminhos, config, estado, motor


@dataclass
class Receita:
    ident: str
    nome: str
    titulo: str
    passos: list[dict]
    requer: list[str] = field(default_factory=list)
    afetada_por: list[str] = field(default_factory=list)
    arquivo: Path | None = None
    # [[desfazer]]: passos que o desfazer.py roda para o que o diario nao cobre
    desfazer: list[dict] = field(default_factory=list)

    @property
    def aplicada(self) -> bool:
        return estado.aplicado(self.ident)

    def como_dict(self) -> dict:
        return {"id": self.ident, "nome": self.nome, "titulo": self.titulo,
                "requer": self.requer, "afetada_por": self.afetada_por,
                "aplicada": self.aplicada, "quando": estado.quando(self.ident)}


def carregar() -> list[Receita]:
    """Todas as receitas, na ordem do numero no nome do arquivo."""
    saida: list[Receita] = []
    for arquivo in sorted(caminhos.RECEITAS.glob("*.toml")):
        try:
            dados = tomllib.loads(arquivo.read_text())
        except (OSError, tomllib.TOMLDecodeError) as erro:
            estado.registrar(f"receita invalida {arquivo.name}: {erro}")
            continue
        cabecalho = dados.get("modulo", {})
        ident = str(cabecalho.get("id") or arquivo.stem.split("-")[0])
        saida.append(Receita(
            ident=ident,
            nome=cabecalho.get("nome", arquivo.stem),
            titulo=cabecalho.get("titulo", ""),
            passos=dados.get("passo", []),
            requer=[str(x) for x in cabecalho.get("requer", [])],
            afetada_por=[str(x) for x in cabecalho.get("afetada_por", [])],
            arquivo=arquivo,
            desfazer=dados.get("desfazer", []),
        ))
    return saida


def por_id() -> dict[str, Receita]:
    return {r.ident: r for r in carregar()}


NUCLEO = ("10", "30", "31")


def instalado(lista: list[Receita] | None = None) -> bool:
    """A maquina ja foi preparada? Basta o nucleo estar aplicado."""
    feitas = {r.ident for r in (lista or carregar()) if r.aplicada}
    return all(n in feitas for n in NUCLEO)


def afetadas_por(chaves: list[str]) -> list[str]:
    """Quais receitas reexecutar quando essas preferencias mudam."""
    alvos = {r.ident for r in carregar()
             if any(c in r.afetada_por for c in chaves)}
    return sorted(alvos, key=lambda x: (len(x), x))


def desatualizadas(lista: list[Receita] | None = None) -> set[str]:
    """Receitas nunca aplicadas, ou cujo arquivo mudou depois de aplicadas.

    Sem isso, uma receita nova ou reescrita nunca chega ao sistema enquanto
    ninguem mexer numa opcao que a afete.
    """
    saida: set[str] = set()
    for r in lista or carregar():
        marca = estado.marca(r.ident)
        try:
            if not marca.is_file() or (
                    r.arquivo and r.arquivo.stat().st_mtime > marca.stat().st_mtime):
                saida.add(r.ident)
        except OSError:
            continue
    return saida


def selecionar(todas: list[Receita], apenas: list[str] | None,
               pular: list[str] | None) -> list[Receita]:
    escolhidas = todas
    if apenas:
        alvo = {x.strip() for x in apenas if x.strip()}
        escolhidas = [r for r in escolhidas if r.ident in alvo or r.nome in alvo]
    if pular:
        fora = {x.strip() for x in pular if x.strip()}
        escolhidas = [r for r in escolhidas if r.ident not in fora and r.nome not in fora]
    return escolhidas


def executar(apenas: list[str] | None = None, pular: list[str] | None = None,
             refazer: bool = False, simular: bool = False,
             saida: Callable[[str], None] | None = None,
             cfg: dict[str, str] | None = None) -> int:
    """Roda as receitas escolhidas. Devolve quantas falharam."""
    diz = saida or print
    try:
        with caminhos.trava():
            return _executar(apenas, pular, refazer, simular, diz, cfg)
    except caminhos.Ocupado as erro:
        diz(f"{erro}; espere terminar")
        return 1


def _executar(apenas, pular, refazer, simular, diz, cfg) -> int:
    caminhos.preparar()
    cfg = cfg or config.ler()
    ctx = motor.montar_contexto(cfg)
    escolhidas = selecionar(carregar(), apenas, pular)
    if not escolhidas:
        diz("nenhuma receita corresponde ao pedido")
        return 0

    falhas = 0
    for receita in escolhidas:
        if receita.aplicada and not refazer:
            diz(f"  ja aplicado: {receita.ident} {receita.titulo}")
            continue
        faltando = [x for x in receita.requer if not estado.aplicado(x)]
        if faltando and not simular:
            diz(f"  pulando {receita.ident} {receita.titulo}: "
                f"depende de {', '.join(faltando)}")
            falhas += 1
            continue

        diz(f"\n==> {receita.ident} {receita.titulo}")
        # o contexto e refeito a cada receita: o papel de parede e o fundo do login
        # so existem depois que a receita de papeis baixou as imagens
        ctx = motor.montar_contexto(cfg)
        maquina = motor.Motor(ctx, saida=diz, simular=simular, receita=receita.ident)
        try:
            maquina.rodar(receita.passos)
        except motor.ErroDePasso as erro:
            diz(f"  ERRO: {erro}")
            falhas += 1
            continue
        except Exception as erro:                      # nao derruba o resto
            diz(f"  ERRO inesperado: {erro}")
            estado.registrar(f"erro inesperado em {receita.ident}: {erro!r}")
            falhas += 1
            continue
        if not simular:
            estado.marcar(receita.ident)
        diz(f"  concluido: {receita.titulo}")
    return falhas
