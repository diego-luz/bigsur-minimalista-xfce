"""Executa os passos de uma receita.

Cada passo e um dicionario com um campo `tipo`. O motor sabe executar uns
poucos tipos bem definidos, e `script` fica como valvula de escape para o que
nao vale a pena descrever em dados.

Todo texto passa por substituicao com o contexto, entao a receita escreve
`WhiteSur-@@gtk_variante@@` e o motor resolve.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Iterable

from . import caminhos, estado, papeis, sistema

Saida = Callable[[str], None]


# --------------------------------------------------------------------------
# contexto: os valores que as receitas podem interpolar
# --------------------------------------------------------------------------

# As preferencias tem nome em portugues, mas os instaladores de terceiros
# esperam o nome em ingles. A traducao fica aqui, e nao dentro da receita, para
# nao espalhar essa conversao por varios lugares.
DESTAQUE_EXTERNO = {
    "padrao": "default", "azul": "blue", "roxo": "purple", "rosa": "pink",
    "vermelho": "red", "laranja": "orange", "amarelo": "yellow",
    "verde": "green", "cinza": "grey",
}


def montar_contexto(cfg: dict[str, str]) -> dict[str, str]:
    escuro = cfg.get("tema") == "escuro"
    logo = cfg.get("logo", "debian")

    # o desenho do logo e o oposto do fundo: painel escuro pede desenho claro
    if logo.endswith("-cor"):
        arquivo_logo = f"{logo[:-4]}-cor.svg"
    else:
        arquivo_logo = f"{logo}-{'claro' if escuro else 'escuro'}.svg"

    # O WhiteSur nomeia o tema com a cor no fim, como WhiteSur-Dark-red, e so
    # a cor padrao fica sem sufixo. Sem isso o tema compilado com a cor
    # escolhida existe no disco mas nunca chega a ser usado.
    destaque = DESTAQUE_EXTERNO.get(cfg.get("destaque", "padrao"), "default")
    sufixo = "" if destaque == "default" else f"-{destaque}"
    variante = "Dark" if escuro else "Light"

    # A tela de login fica sempre sobre a variante escura: os campos sao de
    # vidro claro sobre uma foto, e os menus do topo precisam de texto branco.
    temas = Path("/usr/share/themes")
    login_tema = temas / f"WhiteSur-Dark{sufixo}" / "gtk-3.0/gtk.css"
    if not login_tema.is_file():
        login_tema = temas / "WhiteSur-Dark" / "gtk-3.0/gtk.css"

    # o lightdm nao le a pasta pessoal, que no Debian e fechada; a foto vai
    # para /usr/share na instalacao
    face = Path.home() / ".face"
    avatar = face if face.is_file() else caminhos.ARQUIVOS / "logos" / "debian-claro.svg"

    minutos = cfg.get("bloqueio", "10")

    ctx: dict[str, str] = dict(cfg)
    ctx.update({
        "HOME": str(Path.home()),
        "USUARIO": os.environ.get("USER", ""),
        "gtk_variante": variante,
        "gtk_tema": f"WhiteSur-{variante}{sufixo}",
        "gtk_tema_base": f"WhiteSur-{variante}",
        "gtk_sufixo": sufixo,
        "gtk_escuro": "true" if escuro else "false",
        # e o que os apps libadwaita e o portal consultam para escolher a cor
        "gtk_esquema": "prefer-dark" if escuro else "default",
        # os icones de acao do WhiteSur claro sao cinza escuro e somem nas
        # barras do tema escuro, entao a variante acompanha o tema
        "icones": "WhiteSur-dark" if escuro else "WhiteSur",
        "cursores": "WhiteSur-cursors",
        # as duas variantes ficam na mesma pasta Kvantum/WhiteSur
        "kvantum_tema": "WhiteSurDark" if escuro else "WhiteSur",
        "logo_arquivo": str(caminhos.ARQUIVOS / "logos" / arquivo_logo),
        "painel_fundo": "0.11 0.11 0.13 0.55" if escuro else "0.97 0.97 0.99 0.72",
        "painel_texto": "#f2f2f7" if escuro else "#1d1d1f",
        "fonte_ui": "SF Pro Display" if cfg.get("fonte_interface") == "sf-pro" else "Inter",
        "fonte_mono": "Fira Code",
        "destaque_externo": destaque,
        "papel_arquivo": str(papeis.escolhido(cfg) or ""),
        # login_dir e onde os arquivos sao montados, numa pasta temporaria que
        # a receita apaga ao terminar, sem deixar nada na pasta pessoal;
        # login_raiz e onde o greeter os enxerga. A previa troca os dois e
        # desliga login_instalar
        "login_dir": str(Path(tempfile.gettempdir()) / f"d3bian-init-login-{os.getuid()}"),
        "login_raiz": "/usr/share/backgrounds/d3bian-init",
        "login_instalar": "sim",
        "login_tema_base": str(login_tema),
        "login_fundo_arquivo": str(papeis.fundo_login(cfg) or ""),
        "login_avatar_arquivo": str(avatar),
        "login_esconder_usuarios": "false" if cfg.get("login_usuarios") == "lista" else "true",
        "bloqueio_segundos": str(int(minutos) * 60) if minutos.isdigit() else "0",
        "fontes": str(caminhos.FONTES),
        "arquivos": str(caminhos.ARQUIVOS),
    })
    return ctx


# @@chave@@ em vez de {chave}: as chaves colidiriam com a sintaxe do
# conky, do CSS e do shell, que aparecem nos modelos
_CHAVE = re.compile(r"@@([a-zA-Z_][a-zA-Z0-9_]*)@@")


def resolver(valor, ctx: dict[str, str]):
    """Troca @@chave@@ pelo valor do contexto, em textos e dentro de listas."""
    if isinstance(valor, str):
        return _CHAVE.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), valor)
    if isinstance(valor, list):
        return [resolver(x, ctx) for x in valor]
    if isinstance(valor, dict):
        return {c: resolver(v, ctx) for c, v in valor.items()}
    return valor


def condicao_atende(expressao: str, ctx: dict[str, str]) -> bool:
    """Avalia `chave == valor` ou `chave != valor`. Nada alem disso, de proposito."""
    for operador, esperado in ((" != ", False), (" == ", True)):
        if operador in expressao:
            chave, _, alvo = expressao.partition(operador)
            igual = ctx.get(chave.strip(), "") == alvo.strip().strip('"\'')
            return igual is esperado
    return bool(ctx.get(expressao.strip()))


# --------------------------------------------------------------------------
# motor
# --------------------------------------------------------------------------

class ErroDePasso(Exception):
    pass


class Motor:
    def __init__(self, ctx: dict[str, str], saida: Saida | None = None,
                 simular: bool = False) -> None:
        self.ctx = ctx
        self.simular = simular
        self._saida = saida or (lambda t: None)

    # ---- utilidades ------------------------------------------------------
    def diz(self, texto: str) -> None:
        self._saida(texto)
        estado.registrar(texto)

    def _executa(self, argumentos: list[str], root: bool = False,
                 entrada: str | None = None) -> int:
        if root:
            argumentos = ["sudo", "-n", *argumentos]
        if self.simular:
            self.diz("  [simulacao] " + " ".join(shlex.quote(a) for a in argumentos))
            return 0
        estado.registrar("+ " + " ".join(shlex.quote(a) for a in argumentos))
        try:
            proc = subprocess.run(
                argumentos, input=entrada, capture_output=True, text=True,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive", "TERM": "dumb"},
            )
        except OSError as erro:
            raise ErroDePasso(f"nao consegui executar {argumentos[0]}: {erro}") from erro
        for linha in (proc.stdout or "").splitlines():
            estado.registrar("  " + linha)
        if proc.returncode != 0:
            for linha in (proc.stderr or "").splitlines()[-8:]:
                self.diz("  " + linha)
        return proc.returncode

    def _caminho(self, bruto: str) -> Path:
        return Path(resolver(bruto, self.ctx)).expanduser()

    # ---- passos ----------------------------------------------------------
    def passo_apt(self, p: dict) -> None:
        pedidos = [x for x in resolver(p.get("pacotes", []), self.ctx) if x]
        faltam, inexistentes = [], []
        estados = sistema.estado_pacotes(pedidos)
        for nome in pedidos:
            info = estados.get(nome, {})
            if info.get("instalado"):
                continue
            (faltam if info.get("disponivel") else inexistentes).append(nome)
        if inexistentes:
            self.diz(f"  nao existem no repositorio, ignorados: {', '.join(inexistentes)}")
        if not faltam:
            self.diz("  pacotes ja presentes")
            return
        self.diz(f"  instalando: {', '.join(faltam)}")
        codigo = self._executa(["apt-get", "install", "-y", "--no-install-recommends",
                                *faltam], root=True)
        if codigo != 0:
            raise ErroDePasso(f"apt-get falhou ao instalar {', '.join(faltam)}")

    def passo_xfconf(self, p: dict) -> None:
        canal = resolver(p["canal"], self.ctx)
        chave = resolver(p["chave"], self.ctx)
        # "tipo" ja e o tipo do passo; o tipo do valor do xfconf vem em
        # "tipo_valor", senao um sobrescreve o outro
        tipo = p.get("tipo_valor", "string")
        valor = resolver(p["valor"], self.ctx)
        valores = valor.split() if tipo == "double-array" else [str(valor)]
        tipos = ["double"] * len(valores) if tipo == "double-array" else [tipo]
        args = ["xfconf-query", "-c", canal, "-p", chave]
        for t in tipos:
            args += ["-t", t]
        for v in valores:
            args += ["-s", v]
        if self._executa([*args, "-n"]) != 0 and self._executa(args) != 0:
            # a propriedade pode existir com outro tipo; recria
            self._executa(["xfconf-query", "-c", canal, "-p", chave, "-r"])
            if self._executa([*args, "-n"]) != 0:
                self.diz(f"  nao consegui definir {canal}{chave}")

    def passo_arquivo(self, p: dict) -> None:
        destino = self._caminho(p["destino"])
        if p.get("modelo"):
            origem = caminhos.ARQUIVOS / resolver(p["modelo"], self.ctx)
            try:
                conteudo = origem.read_text()
            except OSError as erro:
                raise ErroDePasso(f"modelo ausente: {origem}") from erro
        else:
            conteudo = p.get("conteudo", "")
        conteudo = resolver(conteudo, self.ctx)
        estado.copia_de_seguranca(destino)
        if self.simular:
            self.diz(f"  [simulacao] escreveria {destino}")
            return
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo)
        if p.get("modo"):
            destino.chmod(int(str(p["modo"]), 8))
        self.diz(f"  escrito {destino}")

    def passo_bloco(self, p: dict) -> None:
        """Insere ou troca um trecho marcado dentro de um arquivo existente."""
        destino = self._caminho(p["destino"])
        marca = resolver(p.get("marca", "d3bian-init"), self.ctx)
        conteudo = resolver(p.get("conteudo", ""), self.ctx)
        abre, fecha = f"/* {marca} */", f"/* fim {marca} */"
        if p.get("comentario") == "#":
            abre, fecha = f"# {marca}", f"# fim {marca}"
        estado.copia_de_seguranca(destino)
        if self.simular:
            self.diz(f"  [simulacao] bloco '{marca}' em {destino}")
            return
        destino.parent.mkdir(parents=True, exist_ok=True)
        texto = destino.read_text() if destino.exists() else ""
        texto = re.sub(re.escape(abre) + r".*?" + re.escape(fecha), "", texto, flags=re.S)
        texto = texto.rstrip() + f"\n\n{abre}\n{conteudo.strip()}\n{fecha}\n"
        destino.write_text(texto)
        self.diz(f"  bloco '{marca}' em {destino}")

    def passo_git(self, p: dict) -> None:
        destino = self._caminho(p["destino"])
        url = resolver(p["url"], self.ctx)
        ref = resolver(p.get("ref", "HEAD"), self.ctx)
        if self.simular:
            self.diz(f"  [simulacao] clonaria {url} em {destino}")
            return
        destino.parent.mkdir(parents=True, exist_ok=True)
        if (destino / ".git").is_dir():
            self.diz(f"  atualizando {destino.name}")
            self._executa(["git", "-C", str(destino), "remote", "set-url", "origin", url])
            if self._executa(["git", "-C", str(destino), "fetch", "--depth", "1",
                              "origin", ref]) == 0:
                self._executa(["git", "-C", str(destino), "checkout", "-f", "FETCH_HEAD"])
            return
        self.diz(f"  clonando {destino.name}")
        if self._executa(["git", "clone", "--depth", "1", "--branch", ref, url,
                          str(destino)]) != 0:
            if self._executa(["git", "clone", "--depth", "1", url, str(destino)]) != 0:
                raise ErroDePasso(f"nao consegui clonar {url}")

    def passo_comando(self, p: dict) -> None:
        argumentos = [str(x) for x in resolver(p["argumentos"], self.ctx)]
        codigo = self._executa(argumentos, root=bool(p.get("root")))
        if codigo != 0 and not p.get("tolera_falha"):
            raise ErroDePasso(f"comando falhou ({codigo}): {' '.join(argumentos)}")

    def passo_script(self, p: dict) -> None:
        """Trecho de shell. Usado onde descrever em dados custaria mais que ajudar."""
        corpo = resolver(p["corpo"], self.ctx)
        if self.simular:
            self.diz("  [simulacao] rodaria um trecho de shell")
            return
        ambiente = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
        for chave, valor in self.ctx.items():
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", chave):
                ambiente[f"D3_{chave.upper()}"] = str(valor)
        estado.registrar("+ shell:\n" + corpo)
        proc = subprocess.run(["bash", "-euo", "pipefail", "-c", corpo],
                              capture_output=True, text=True, env=ambiente)
        for linha in (proc.stdout or "").splitlines():
            self.diz("  " + linha)
        if proc.returncode != 0:
            for linha in (proc.stderr or "").splitlines()[-10:]:
                self.diz("  " + linha)
            if not p.get("tolera_falha"):
                raise ErroDePasso(f"o trecho de shell falhou ({proc.returncode})")

    def passo_copiar(self, p: dict) -> None:
        origem = self._caminho(p["origem"])
        destino = self._caminho(p["destino"])
        if not origem.exists():
            # na simulacao o passo git nao clona, entao a origem pode so faltar ainda
            if self.simular:
                self.diz(f"  [simulacao] copiaria {origem} para {destino} (origem ainda nao existe)")
                return
            if p.get("tolera_falha"):
                self.diz(f"  origem ausente, ignorando: {origem}")
                return
            raise ErroDePasso(f"origem nao existe: {origem}")
        if self.simular:
            self.diz(f"  [simulacao] copiaria {origem} para {destino}")
            return
        if p.get("root"):
            self._executa(["mkdir", "-p", str(destino.parent)], root=True)
            self._executa(["rm", "-rf", str(destino)], root=True)
            if self._executa(["cp", "-a", str(origem), str(destino)], root=True) != 0:
                raise ErroDePasso(f"nao consegui copiar para {destino}")
        else:
            destino.parent.mkdir(parents=True, exist_ok=True)
            if destino.exists() and destino.is_dir():
                shutil.rmtree(destino, ignore_errors=True)
            if origem.is_dir():
                shutil.copytree(origem, destino, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.copy2(origem, destino)
        self.diz(f"  copiado para {destino}")

    def passo_autostart(self, p: dict) -> None:
        ident = resolver(p["id"], self.ctx)
        arquivo = Path.home() / ".config/autostart" / f"{ident}.desktop"
        if p.get("remover"):
            if not self.simular:
                arquivo.unlink(missing_ok=True)
            self.diz(f"  inicializacao automatica removida: {ident}")
            return
        conteudo = (
            "[Desktop Entry]\nType=Application\n"
            f"Name={resolver(p.get('nome', ident), self.ctx)}\n"
            f"Exec={resolver(p['comando'], self.ctx)}\n"
            "Terminal=false\nX-GNOME-Autostart-enabled=true\n"
            f"X-GNOME-Autostart-Delay={p.get('atraso', 3)}\n"
        )
        if self.simular:
            self.diz(f"  [simulacao] inicializacao automatica: {ident}")
            return
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(conteudo)
        self.diz(f"  inicializacao automatica: {ident}")

    def passo_processo(self, p: dict) -> None:
        """Para, inicia ou reinicia um programa da sessao grafica."""
        nome = resolver(p["nome"], self.ctx)
        acao = p.get("acao", "reiniciar")
        if self.simular:
            self.diz(f"  [simulacao] {acao} {nome}")
            return
        if acao in ("parar", "reiniciar"):
            subprocess.run(["pkill", "-x", nome], capture_output=True)
        if acao in ("iniciar", "reiniciar"):
            argumentos = [str(x) for x in resolver(p.get("argumentos", [nome]), self.ctx)]
            try:
                subprocess.Popen(["setsid", "--fork", *argumentos],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
            except OSError as erro:
                self.diz(f"  nao consegui iniciar {nome}: {erro}")
                return
        self.diz(f"  {acao}: {nome}")

    def passo_backup(self, p: dict) -> None:
        for bruto in resolver(p.get("caminhos", []), self.ctx):
            if estado.copia_de_seguranca(Path(bruto).expanduser()):
                self.diz(f"  guardado: {bruto}")

    # ---- despacho --------------------------------------------------------
    TIPOS = {
        "apt": passo_apt, "xfconf": passo_xfconf, "arquivo": passo_arquivo,
        "bloco": passo_bloco, "git": passo_git, "comando": passo_comando,
        "script": passo_script, "copiar": passo_copiar,
        "autostart": passo_autostart, "processo": passo_processo,
        "backup": passo_backup,
    }

    def rodar(self, passos: Iterable[dict]) -> None:
        for passo in passos:
            tipo = passo.get("tipo")
            funcao = self.TIPOS.get(tipo)
            if funcao is None:
                raise ErroDePasso(f"tipo de passo desconhecido: {tipo}")
            condicao = passo.get("se")
            if condicao and not condicao_atende(str(condicao), self.ctx):
                continue
            if passo.get("dizer"):
                self.diz(resolver(passo["dizer"], self.ctx))
            funcao(self, passo)
