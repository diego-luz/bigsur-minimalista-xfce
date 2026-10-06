"""Volta a maquina ao que era antes do projeto.

Tres etapas, e uma quarta opcional:

- d1: os [[desfazer]] de cada receita aplicada, da ultima para a primeira. E ali
  que fica o que nenhum passo generico sabe desfazer: chsh, gsettings, extensao
  habilitada, servico ligado.
- d2: o diario de tras para frente. Arquivo criado sai; arquivo que ja existia
  volta da copia de seguranca; bloco sai do arquivo e o resto fica; xfconf,
  gsettings e dconf voltam ao valor de antes; processo que o projeto iniciou e
  nao rodava antes para. Downloads e clones na pasta de dados do projeto ficam
  para o d4, que apaga a pasta inteira.
- d3: as marcas de etapa aplicada, e a pagina volta a oferecer a instalacao.
- d4 (so com apagar): os pacotes que o projeto instalou, e as pastas do projeto
  (opcoes, log, copias, downloads). Pacote que levaria outros programas junto
  fica, e o que da o shell do login tambem.

Maquina instalada antes de existir o diario: d2 so devolve as copias de
seguranca, e os pacotes vem do historico do apt.
"""

from __future__ import annotations

import getpass
import gzip
import os
import pwd
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import caminhos, config, diario, estado, motor, receitas, sistema

Diz = Callable[[str], None]

ETAPAS = [
    ("d1", "O que cada receita pede para desfazer"),
    ("d2", "Arquivos, blocos e configuracoes"),
    ("d3", "Etapas marcadas como aplicadas"),
]
ETAPA_APAGAR = ("d4", "Remover o que foi instalado")

# nunca apagados, por engano de caminho ou de diario
PROTEGIDOS = {Path("/"), Path.home(), Path("/usr"), Path("/etc"), Path("/opt"), Path("/boot"),
              Path("/usr/share"), Path("/usr/local"), Path("/usr/local/bin"),
              Path.home() / ".config", Path.home() / ".local", Path.home() / ".local/share"}


def etapas(apagar: bool = False) -> list[tuple[str, str]]:
    return ETAPAS + ([ETAPA_APAGAR] if apagar else [])


def _rodar(argumentos: list[str], diz: Diz) -> int:
    estado.registrar("+ " + " ".join(argumentos))
    try:
        proc = subprocess.run(argumentos, capture_output=True, text=True)
    except OSError as erro:
        diz(f"  nao consegui executar {argumentos[0]}: {erro}")
        return 1
    if proc.returncode != 0:
        for linha in (proc.stderr or "").splitlines()[-4:]:
            diz("  " + linha)
    return proc.returncode


def _da_pessoa(caminho: Path) -> bool:
    return caminho == Path.home() or Path.home() in caminho.parents


# ---- d1: desfazer declarado nas receitas ------------------------------------

def _receitas(diz: Diz) -> int:
    ctx = motor.montar_contexto(config.ler())
    no_diario = {e.get("receita") for e in diario.ler()}
    falhas = 0
    for receita in reversed(receitas.carregar()):
        if not receita.desfazer or not (receita.aplicada or receita.ident in no_diario):
            continue
        diz(f"  {receita.ident} {receita.titulo}")
        try:
            motor.Motor(ctx, saida=diz, anotar=False).rodar(receita.desfazer)
        except motor.ErroDePasso as erro:
            diz(f"  ERRO em {receita.ident}: {erro}")
            falhas += 1
    return falhas


# ---- d2: o diario de tras para frente ---------------------------------------

# pastas que o sistema (e outros programas) espera encontrar, mesmo vazias
PASTAS_DO_SISTEMA = {Path.home() / p for p in (
    ".config", ".cache", ".local", ".local/bin", ".local/share", ".local/state",
    ".themes", ".icons", ".fonts", ".local/share/icons", ".local/share/themes",
    ".local/share/fonts", ".local/share/applications", ".local/share/backgrounds")}


def _limpar_vazias(pasta: Path, diz: Diz) -> None:
    """Sobe apagando pasta que ficou vazia, para nao ficar casca do projeto.

    O rmdir so funciona em pasta vazia, entao nada que tenha conteudo de outra
    pessoa ou de outro programa e tocado. Para no que o sistema espera achar,
    na pasta de dados do projeto e na casa.
    """
    casa = Path.home()
    guardadas = {getattr(caminhos, n, None) for n in ("DADOS_DIR", "ESTADO_DIR", "BACKUP")}
    while (pasta != casa and casa in pasta.parents
           and pasta not in PASTAS_DO_SISTEMA and pasta not in PROTEGIDOS
           and not any(g and (pasta == g or g in pasta.parents) for g in guardadas)):
        try:
            pasta.rmdir()
        except OSError:
            return
        diz(f"  pasta vazia {pasta} apagada")
        pasta = pasta.parent


def _apagar(caminho: Path, diz: Diz) -> None:
    if caminho in PROTEGIDOS or len(caminho.parts) < 3:
        diz(f"  atencao: {caminho} nao e apagado (caminho protegido)")
        return
    if not caminho.exists() and not caminho.is_symlink():
        return
    if _da_pessoa(caminho):
        if caminho.is_dir() and not caminho.is_symlink():
            shutil.rmtree(caminho, ignore_errors=True)
        else:
            caminho.unlink(missing_ok=True)
    elif _rodar(["sudo", "-n", "rm", "-rf", str(caminho)], diz) != 0:
        diz(f"  nao consegui apagar {caminho}")
        return
    diz(f"  apagado {caminho}")
    _limpar_vazias(caminho.parent, diz)


def _voltar_copia(caminho: Path, diz: Diz) -> None:
    copia = caminhos.BACKUP / str(caminho).lstrip("/")
    if not copia.exists():
        diz(f"  atencao: sem copia de seguranca de {caminho}; fica como esta")
        return
    if _da_pessoa(caminho):
        if caminho.is_dir() and not caminho.is_symlink():
            shutil.rmtree(caminho, ignore_errors=True)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if copia.is_dir():
            shutil.copytree(copia, caminho, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(copia, caminho)
    else:
        _rodar(["sudo", "-n", "rm", "-rf", str(caminho)], diz)
        if _rodar(["sudo", "-n", "cp", "-a", str(copia), str(caminho)], diz) != 0:
            diz(f"  nao consegui devolver {caminho}")
            return
        # a copia foi feita com o usuario; no sistema, o dono volta a ser o root
        _rodar(["sudo", "-n", "chown", "-R", "root:root", str(caminho)], diz)
    diz(f"  devolvido {caminho}")


def tirar_bloco(arquivo: Path, marca: str, comentario: str) -> bool:
    """Tira o trecho que o passo bloco do motor escreveu, com as mesmas marcas."""
    if not arquivo.is_file():
        return False
    abre, fecha = (f"# {marca}", f"# fim {marca}") if comentario == "#" else (f"/* {marca} */", f"/* fim {marca} */")
    texto = arquivo.read_text()
    novo = re.sub(r"\n*" + re.escape(abre) + r".*?" + re.escape(fecha) + r"\n?", "\n", texto, flags=re.S)
    if novo == texto:
        return False
    arquivo.write_text(novo.strip("\n") + "\n" if novo.strip() else "")
    return True


def _xfconf(item: dict, diz: Diz) -> None:
    if not shutil.which("xfconf-query"):
        return
    base = ["xfconf-query", "-c", item["canal"], "-p", item["chave"]]
    subprocess.run([*base, "-r"], capture_output=True)
    if not item.get("existia"):
        return
    valor = item.get("valor", "")
    tipo = item.get("tipo_valor", "string")
    if valor.startswith("Value is an array"):
        valores = [v for v in valor.split("\n\n", 1)[-1].splitlines() if v.strip()]
        tipo_item = "double" if tipo == "double-array" else "string"
    else:
        valores = [valor.rstrip("\n")]
        tipo_item = tipo
    argumentos = [*base, "-n"]
    for v in valores:
        argumentos += ["-t", tipo_item, "-s", v]
    _rodar(argumentos, diz)


def _canais_vazios(itens: list[dict], diz: Diz) -> None:
    """Canal do xfconf que nao existia e ficou sem propriedades: o arquivo dele sai."""
    if not shutil.which("xfconf-query"):
        return
    pasta = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "xfce4/xfconf/xfce-perchannel-xml"
    for canal in sorted({i["canal"] for i in itens if i.get("tipo") == "xfconf" and i.get("canal_existia") is False}):
        lista = subprocess.run(["xfconf-query", "-c", canal, "-l"], capture_output=True, text=True,
                               env={**os.environ, "LC_ALL": "C"}).stdout
        arquivo = pasta / f"{canal}.xml"
        if not any(l.startswith("/") for l in lista.splitlines()) and arquivo.is_file() \
                and "<property" not in arquivo.read_text(errors="replace"):
            arquivo.unlink()
            diz(f"  apagado {arquivo}, que so existia pelo projeto")


def _diario(diz: Diz) -> int:
    itens = diario.ler()
    if not itens:
        diz("  atencao: esta instalacao e anterior ao diario; so as copias de seguranca voltam")
        feitos = estado.restaurar_tudo()
        diz(f"  {len(feitos)} arquivo(s) devolvido(s)")
        # projetos do GNOME guardam o dconf inteiro de antes
        if getattr(estado, "restaurar_dconf", None) and estado.restaurar_dconf():
            diz("  configuracoes do GNOME de antes carregadas")
        return 0
    falhas = 0
    guardados = 0
    for item in reversed(itens):
        try:
            tipo = item.get("tipo")
            if tipo == "criado" and caminhos.DADOS_DIR in Path(item["caminho"]).parents:
                guardados += 1
            elif tipo == "criado":
                _apagar(Path(item["caminho"]), diz)
            elif tipo == "pasta":
                # criada pelo projeto: sai so se ficou vazia
                try:
                    Path(item["caminho"]).rmdir()
                    diz(f"  pasta vazia {item['caminho']} apagada")
                except OSError:
                    pass
            elif tipo == "alterado":
                _voltar_copia(Path(item["caminho"]), diz)
            elif tipo == "bloco":
                caminho = Path(item["caminho"])
                if tirar_bloco(caminho, item["marca"], item.get("comentario", "")):
                    diz(f"  bloco '{item['marca']}' tirado de {caminho}")
                if item.get("arquivo_novo") and caminho.is_file() and not caminho.read_text().strip():
                    caminho.unlink()
                    _limpar_vazias(caminho.parent, diz)
            elif tipo == "xfconf":
                _xfconf(item, diz)
            elif tipo == "gsettings" and shutil.which("gsettings"):
                # chave que estava no padrao volta a ficar no padrao, e nao gravada com ele
                if item.get("padrao"):
                    _rodar(["gsettings", "reset", item["esquema"], item["chave"]], diz)
                elif item.get("valor"):
                    _rodar(["gsettings", "set", item["esquema"], item["chave"], item["valor"]], diz)
            elif tipo == "dconf" and shutil.which("dconf"):
                if item.get("valor"):
                    _rodar(["dconf", "write", item["chave"], item["valor"]], diz)
                else:
                    _rodar(["dconf", "reset", item["chave"]], diz)
            elif tipo == "processo" and not item.get("rodava"):
                subprocess.run(["pkill", "-x", item["nome"]], capture_output=True)
        except (OSError, KeyError, shutil.Error) as erro:
            diz(f"  ERRO ao desfazer {item.get('tipo')} {item.get('caminho', item.get('chave', ''))}: {erro}")
            falhas += 1
    _canais_vazios(itens, diz)
    if guardados:
        diz(f"  {guardados} download(s) na pasta do projeto ficam; saem com a opcao de remover")
    diz("  diario percorrido")
    return falhas


# ---- d4: remover o que foi instalado ----------------------------------------

def _pacotes_das_receitas() -> set[str]:
    nomes = set()
    for receita in receitas.carregar():
        for passo in receita.passos:
            if passo.get("tipo") == "apt":
                nomes |= {n for n in passo.get("pacotes", []) if "@@" not in n}
    return nomes


def _historico_apt() -> list[str]:
    """Sem diario: pacotes que o painel pediu ao apt, desde o primeiro uso do projeto."""
    usuario = getpass.getuser()
    do_projeto = _pacotes_das_receitas()
    inicio = ""
    try:
        primeira = caminhos.REGISTRO.read_text(errors="replace").split("\n", 1)[0]
        inicio = primeira[1:11] if primeira.startswith("[") else ""
    except OSError:
        pass
    textos = []
    for arquivo in sorted(Path("/var/log/apt").glob("history.log*")):
        try:
            dados = arquivo.read_bytes()
            textos.append((gzip.decompress(dados) if arquivo.suffix == ".gz" else dados).decode(errors="replace"))
        except (OSError, EOFError, gzip.BadGzipFile):
            continue
    achados = set()
    for bloco in "\n\n".join(textos).split("\n\n"):
        data = re.search(r"^Start-Date: (\S+)", bloco, re.M)
        pedido = re.search(r"^Commandline: apt-get install -y --no-install-recommends (.+)$", bloco, re.M)
        por = re.search(r"^Requested-By: (\S+) ", bloco, re.M)
        if not (data and pedido and por) or por.group(1) != usuario:
            continue
        if inicio and data.group(1) < inicio:
            continue
        achados |= set(pedido.group(1).split()) & do_projeto
    return sorted(achados)


def _pacote_do_shell() -> str:
    """Pacote que da o shell do login: remover deixaria a pessoa sem entrar."""
    shell = pwd.getpwnam(getpass.getuser()).pw_shell
    saida = subprocess.run(["dpkg", "-S", os.path.realpath(shell)], capture_output=True, text=True).stdout
    return saida.split(":", 1)[0].strip() if saida else ""


def previa_remocao() -> dict:
    """O que a etapa de remover apagaria, sem mexer em nada. A pagina mostra antes."""
    itens = diario.ler()
    if itens:
        candidatos = sorted({n for e in itens if e.get("tipo") == "pacotes" for n in e.get("nomes", [])})
        origem = "diario"
    else:
        candidatos, origem = _historico_apt(), "historico"
    instalados = {n for n, i in sistema.estado_pacotes(candidatos).items() if i.get("instalado")}
    do_shell = _pacote_do_shell()
    pacotes, ficam = [], []
    for nome in (n for n in candidatos if n in instalados):
        if nome == do_shell:
            ficam.append({"nome": nome, "motivo": "dá o shell do login; volte o shell primeiro"})
            continue
        pacotes.append(nome)
    # o que depende de um pacote so segura ele se nao sair junto; repete porque
    # um pacote que fica pode segurar outro
    mudou = True
    while mudou:
        mudou = False
        for nome in list(pacotes):
            simulado = subprocess.run(["apt-get", "-s", "remove", nome], capture_output=True, text=True,
                                      env={**os.environ, "LC_ALL": "C"}).stdout
            levaria = [x for x in re.findall(r"^Remv (\S+)", simulado, re.M)
                       if x != nome and x.split(":")[0] not in pacotes]
            if levaria:
                pacotes.remove(nome)
                ficam.append({"nome": nome, "motivo": "outros programas dependem dele: " + ", ".join(levaria[:6])
                              + ("…" if len(levaria) > 6 else "")})
                mudou = True
    pastas = [str(p) for p in (caminhos.CONFIG_DIR, caminhos.DADOS_DIR, caminhos.ESTADO_DIR) if p.exists()]
    # dependencias que o apt trouxe junto; so saem as que ninguem mais usa, depois dos pacotes
    dependencias = sorted({d for e in itens if e.get("tipo") == "pacotes" for d in e.get("dependencias", [])}
                          - set(pacotes) - {f["nome"] for f in ficam})
    return {"pacotes": pacotes, "ficam": ficam, "pastas_do_projeto": pastas, "origem": origem,
            "mudancas": len(itens), "dependencias": dependencias}


def _orfas() -> set[str]:
    """Pacotes que o apt autoremove tiraria agora."""
    saida = subprocess.run(["apt-get", "-s", "autoremove"], capture_output=True, text=True,
                           env={**os.environ, "LC_ALL": "C"}).stdout
    return set(re.findall(r"^Remv (\S+)", saida, re.M))


def _dependencias_anotadas(nomes: list[str], diz: Diz) -> None:
    """As que vieram com os pacotes do projeto e o autoremove deixou, por serem so sugeridas."""
    sobram = [n for n, i in sistema.estado_pacotes(nomes).items() if i.get("instalado")]
    # so sai o que nao leva junto nada de fora da lista; repete porque um que fica segura outro
    mudou = True
    while mudou and sobram:
        mudou = False
        for nome in list(sobram):
            simulado = subprocess.run(["apt-get", "-s", "remove", nome], capture_output=True, text=True,
                                      env={**os.environ, "LC_ALL": "C"}).stdout
            if any(x.split(":")[0] not in sobram for x in re.findall(r"^Remv (\S+)", simulado, re.M)):
                sobram.remove(nome)
                mudou = True
    if sobram:
        diz(f"  dependencias que vieram com eles: {', '.join(sobram)}")
        if _rodar(["sudo", "-n", "apt-get", "remove", "-y", *sobram], diz) != 0:
            diz("  atencao: nao consegui tirar essas dependencias")


def _remover(diz: Diz) -> int:
    previa = previa_remocao()
    if previa["origem"] == "historico":
        diz("  atencao: instalacao anterior ao diario; pacotes tirados do historico do apt")
    for item in previa["ficam"]:
        diz(f"  atencao: {item['nome']} fica instalado: {item['motivo']}")
    if previa["pacotes"]:
        # o que ja sobrava antes nao e do projeto e fica
        orfas_antes = _orfas()
        diz(f"  desinstalando com apt: {', '.join(previa['pacotes'])}")
        if _rodar(["sudo", "-n", "apt-get", "remove", "-y", *previa["pacotes"]], diz) != 0:
            diz("  ERRO: apt-get remove falhou; as pastas do projeto ficam")
            return 1
        novas = sorted(_orfas() - orfas_antes)
        if novas:
            diz(f"  dependencias que so estavam ali pelo projeto: {', '.join(novas)}")
            if _rodar(["sudo", "-n", "apt-get", "remove", "-y", *novas], diz) != 0:
                diz("  atencao: nao consegui tirar as dependencias; sudo apt autoremove limpa depois")
        _dependencias_anotadas(previa.get("dependencias", []), diz)
    # por ultimo: o log, o diario e as copias que as etapas anteriores ainda usaram
    for pasta in previa["pastas_do_projeto"]:
        shutil.rmtree(pasta, ignore_errors=True)
        diz(f"  apagado {pasta}")
    return 0


# ---- tudo -----------------------------------------------------------------

def executar(diz: Diz = print, apagar: bool = False) -> int:
    """Desfaz tudo, uma etapa por vez. Devolve quantas falharam."""
    caminhos.preparar()
    passos = {"d1": _receitas, "d2": _diario,
              "d3": lambda d: (estado.limpar_marcas(), d("  a pagina volta a mostrar a instalacao completa"))[0] or 0,
              "d4": _remover}
    falhas = 0
    for ident, titulo in etapas(apagar):
        diz(f"\n==> {ident} {titulo}")
        try:
            erros = int(passos[ident](diz) or 0)
        except Exception as erro:                  # uma etapa nao impede as outras
            diz(f"  ERRO: {erro}")
            estado.registrar(f"desfazer {ident} falhou: {erro!r}")
            falhas += 1
            continue
        if erros:
            falhas += erros
            diz(f"  ERRO: {erros} item(ns) com problema nesta etapa")
            continue
        diz(f"  concluido: {titulo}")
    return falhas
