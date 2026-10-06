"""Linha de comando do d3bian-init-bigsur-minimalista-xfce.

Sem argumento nenhum ele faz o que a maioria quer: pede a senha uma vez e abre
o painel no navegador. Os subcomandos existem para quem prefere terminal, e
para automatizar.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time

from . import VERSAO, caminhos, config, estado, receitas, servidor, sistema


# --------------------------------------------------------------------------
# credencial de administrador
# --------------------------------------------------------------------------

def garantir_sudo(obrigatorio: bool = False) -> bool:
    """Pede a senha uma vez e mantem viva enquanto o programa roda.

    A senha e digitada no terminal, nunca na pagina. O painel so reaproveita a
    credencial que foi autorizada aqui.
    """
    if sistema.sudo_liberado():
        return True
    if not sys.stdin.isatty():
        if obrigatorio:
            print("  preciso de permissao de administrador e nao ha terminal para perguntar")
        return False
    print("  Algumas etapas mexem em pacotes e em /etc.")
    print("  Autorize o administrador uma vez, aqui no terminal.\n")
    try:
        if subprocess.run(["sudo", "-v"]).returncode != 0:
            return False
    except OSError:
        return False

    def manter() -> None:
        while True:
            time.sleep(50)
            subprocess.run(["sudo", "-n", "true"], capture_output=True)

    threading.Thread(target=manter, daemon=True).start()
    return True


# --------------------------------------------------------------------------
# subcomandos
# --------------------------------------------------------------------------

def cmd_web(args) -> int:
    garantir_sudo()
    return servidor.subir(porta=args.porta, abrir=not args.sem_navegador)


def cmd_listar(_args) -> int:
    lista = receitas.carregar()
    print(f"  {'id':<5}{'etapa':<22}{'situacao'}")
    for r in lista:
        situacao = f"aplicada em {r.quando}" if False else (
            f"aplicada {estado.quando(r.ident)}" if r.aplicada else "pendente")
        print(f"  {r.ident:<5}{r.nome:<22}{situacao}")
        if r.titulo:
            print(f"  {'':<5}{r.titulo}")
    print(f"\n  preparado: {'sim' if receitas.instalado(lista) else 'nao'}")
    return 0


def cmd_aplicar(args) -> int:
    if not args.simular:
        garantir_sudo()
    falhas = receitas.executar(
        apenas=args.apenas.split(",") if args.apenas else None,
        pular=args.pular.split(",") if args.pular else None,
        refazer=args.refazer or bool(args.apenas),
        simular=args.simular,
    )
    if falhas:
        print(f"\n  {falhas} etapa(s) com problema. Detalhes em {caminhos.REGISTRO}")
        return 1
    print("\n  tudo aplicado")
    return 0


def cmd_instalar(args) -> int:
    impedem = sistema.impedimentos()
    if impedem and not args.mesmo_assim:
        print("  verificacoes que impedem a instalacao: " + ", ".join(impedem))
        print("  use --mesmo-assim para tentar do jeito que esta")
        return 1
    garantir_sudo(obrigatorio=True)
    falhas = receitas.executar()
    print("\n  " + ("instalado" if not falhas else f"{falhas} etapa(s) com problema"))
    print("  encerre a sessao e entre de novo para a barra do topo funcionar por completo")
    return 1 if falhas else 0


def cmd_config(args) -> int:
    if not args.pares:
        atual = config.ler()
        for opcao in config.OPCOES:
            valores = "|".join(opcao.valores) if not opcao.livre else "texto livre"
            print(f"  {opcao.chave:<18}{atual[opcao.chave]:<12}({valores})")
            print(f"  {'':<18}{opcao.titulo}")
        return 0
    novos = {}
    for par in args.pares:
        chave, _, valor = par.partition("=")
        novos[chave.strip()] = valor.strip()
    validos = config.filtrar(novos)
    recusados = sorted(set(novos) - set(validos))
    if recusados:
        print("  recusados: " + ", ".join(recusados))
    mudou = config.gravar(validos)
    print("  alterado: " + (", ".join(mudou) if mudou else "nada"))
    if mudou and not args.so_gravar:
        alvos = receitas.afetadas_por(mudou)
        if alvos:
            garantir_sudo()
            receitas.executar(apenas=alvos, refazer=True)
    return 0


def cmd_verificar(_args) -> int:
    lista = sistema.verificacoes()
    for c in lista:
        marca = "ok " if c["ok"] else ("!! " if c["critico"] else " ~ ")
        print(f"  {marca} {c['nome']:<28}{c['detalhe']}")
    impedem = sistema.impedimentos(lista)
    print("\n  " + ("pronto para instalar" if not impedem
                    else "impedimentos: " + ", ".join(impedem)))
    return 1 if impedem else 0


def cmd_capturar(args) -> int:
    from . import capturas
    if args.login:
        return capturas.previa_login(print)
    if args.todas:
        garantir_sudo()
        return capturas.capturar_todas(print, args.espera)
    return capturas.capturar_atual(print, args.espera)


def cmd_restaurar(args) -> int:
    from . import desfazer
    if args.apagar:
        previa = desfazer.previa_remocao()
        print("  com --apagar, tambem sera apagado:")
        if previa["pacotes"]:
            print(f"    pacotes desinstalados com apt: {', '.join(previa['pacotes'])}")
        for arquivo in previa.get("fontes_externas", []):
            print(f"    {arquivo}")
        for pasta in previa["pastas_do_projeto"]:
            print(f"    {pasta}")
        for item in previa["ficam"]:
            print(f"    fica: {item['nome']} ({item['motivo']})")
        for item in previa.get("conferir", []):
            print(f"    confira a mao (pode ter existido antes): {item}")
    if not args.sim:
        print("  isto volta a maquina ao que era antes: desfaz o que as receitas declaram e o")
        print("  diario de alteracoes." + ("" if args.apagar else " Pacotes instalados ficam (--apagar remove)."))
        print("  confirme com: d3bian-init-bigsur-minimalista-xfce restaurar --sim" + (" --apagar" if args.apagar else ""))
        return 1
    garantir_sudo()
    falhas = desfazer.executar(lambda texto: print(texto), apagar=args.apagar)
    print("\n  pronto; encerre a sessao e entre de novo para completar" if not falhas
          else f"\n  {falhas} problema(s); veja as linhas acima")
    return 1 if falhas else 0


# --------------------------------------------------------------------------

def construir() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="d3bian-init-bigsur-minimalista-xfce",
        description="Prepara e ajusta um Debian com XFCE por uma pagina local.")
    p.add_argument("--versao", action="version", version=f"d3bian-init-bigsur-minimalista-xfce {VERSAO}")
    sub = p.add_subparsers(dest="comando")

    w = sub.add_parser("web", help="abre o painel no navegador (padrao)")
    w.add_argument("--porta", type=int, default=servidor.PORTA_PADRAO)
    w.add_argument("--sem-navegador", action="store_true")
    w.set_defaults(func=cmd_web)

    l = sub.add_parser("listar", help="mostra as etapas e o que ja foi aplicado")
    l.set_defaults(func=cmd_listar)

    a = sub.add_parser("aplicar", help="roda etapas")
    a.add_argument("--apenas", help="ids ou nomes separados por virgula")
    a.add_argument("--pular", help="ids ou nomes separados por virgula")
    a.add_argument("--refazer", action="store_true", help="refaz o que ja foi aplicado")
    a.add_argument("--simular", action="store_true", help="mostra sem alterar nada")
    a.set_defaults(func=cmd_aplicar)

    i = sub.add_parser("instalar", help="instalacao completa, do zero")
    i.add_argument("--mesmo-assim", action="store_true",
                   help="ignora as verificacoes previas")
    i.set_defaults(func=cmd_instalar)

    c = sub.add_parser("config", help="le ou muda preferencias")
    c.add_argument("pares", nargs="*", help="chave=valor")
    c.add_argument("--so-gravar", action="store_true", help="nao reaplica nada")
    c.set_defaults(func=cmd_config)

    v = sub.add_parser("verificar", help="checagens previas")
    v.set_defaults(func=cmd_verificar)

    k = sub.add_parser("capturar", help="atualiza as previas com a sua tela")
    k.add_argument("--todas", action="store_true")
    k.add_argument("--login", action="store_true")
    k.add_argument("--espera", type=int, default=5)
    k.set_defaults(func=cmd_capturar)

    r = sub.add_parser("restaurar", help="volta a maquina ao que era antes do projeto")
    r.add_argument("--apagar", action="store_true",
                   help="remove tambem os pacotes que o projeto instalou e as pastas do projeto")
    r.add_argument("--sim", action="store_true", help="confirma")
    r.set_defaults(func=cmd_restaurar)

    return p


def main(argv: list[str] | None = None) -> int:
    caminhos.preparar()
    caminhos.proteger_codigo()
    parser = construir()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["web", *(argv or [])])
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\n  interrompido")
        return 130
