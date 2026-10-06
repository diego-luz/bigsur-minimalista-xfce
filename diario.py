"""Diario do que as receitas mudaram na maquina.

Cada passo do motor que mexe em algo anota aqui uma linha JSON: arquivo criado
ou alterado, bloco escrito, valor de antes do xfconf, gsettings ou dconf,
pacotes instalados. O desfazer.py percorre o diario de tras para frente, entao,
quando a mesma coisa mudou mais de uma vez, a ultima a ser desfeita e a mais
antiga, e o que volta e o estado de antes do projeto.

Script de receita nao passa pelo motor: ele anota pelas funcoes que o motor poe
no comeco de todo script, antes de mexer em algo, e elas chamam este modulo:

    d3_antes CAMINHO...          arquivo ou pasta: copia se existe, senao "criado"
    d3_gsettings ESQUEMA CHAVE   guarda o valor de agora
    d3_dconf /CAMINHO/CHAVE      guarda o valor de agora (vazio: estava no padrao)
    d3_xfconf CANAL /CHAVE TIPO  guarda o valor de agora e se existia
    d3_processo NOME             guarda se ja rodava antes de iniciar
    d3_criado CAMINHO...         o que so se sabe depois de criado (um perfil novo)
    d3_pacotes NOME...           pacotes que o script instalou e nao existiam antes

A simulacao nao anota nada, e o proprio desfazer roda sem anotar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import caminhos, estado


def arquivo() -> Path:
    return caminhos.ESTADO_DIR / "diario.jsonl"


def anotar(tipo: str, **dados) -> None:
    caminhos.preparar()
    linha = {"quando": estado._agora(), "tipo": tipo, **dados}
    try:
        with arquivo().open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError as erro:
        estado.registrar(f"nao consegui anotar no diario: {erro}")


def ler() -> list[dict]:
    try:
        linhas = arquivo().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    itens = []
    for linha in linhas:
        try:
            item = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        # o diario fica numa pasta do usuario: caminho relativo ou com ".."
        # (/usr/share/themes/../../etc) nao chega ao desfazer
        if "caminho" in item and not caminho_limpo(item["caminho"]):
            continue
        if "criados" in item:
            item["criados"] = [c for c in item.get("criados") or [] if caminho_limpo(c)]
        itens.append(item)
    return itens


def caminho_limpo(bruto) -> bool:
    """Absoluto e ja normalizado (sem "..", "." ou barras repetidas)."""
    return (isinstance(bruto, str) and bruto.startswith("/")
            and os.path.normpath(bruto) == bruto)


def existe() -> bool:
    return arquivo().is_file()


# ---- o valor de agora, antes de mudar -----------------------------------------

def _saida(argumentos: list[str]) -> tuple[int, str]:
    try:
        # em ingles: o desfazer reconhece "Value is an array" do xfconf-query
        proc = subprocess.run(argumentos, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"})
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout


def _criado_pelo_projeto(caminho: Path) -> bool:
    """Ja anotado como criado (ele ou uma pasta acima): um Aplicar depois da instalacao
    nao pode guardar como "de antes" o que o proprio projeto pos ali."""
    alvos = {str(caminho), *(str(p) for p in caminho.parents)}
    return any(i.get("tipo") == "criado" and i.get("caminho") in alvos for i in ler())


def antes_do_caminho(caminho: Path, receita: str = "") -> None:
    caminho = Path(caminho).expanduser()
    if _criado_pelo_projeto(caminho):
        return
    if caminho.exists() or caminho.is_symlink():
        estado.copia_de_seguranca(caminho)
        anotar("alterado", receita=receita, caminho=str(caminho))
    else:
        anotar("criado", receita=receita, caminho=str(caminho))


def antes_do_gsettings(esquema: str, chave: str, receita: str = "") -> None:
    if not shutil.which("gsettings"):
        return
    codigo, valor = _saida(["gsettings", "get", esquema, chave])
    if codigo != 0:
        return
    # o gsettings get devolve o padrao quando a chave nunca foi gravada, e nao ha
    # como diferenciar por ele; quem sabe e o dconf, no caminho do esquema
    caminho = "/" + esquema.replace(".", "/") + "/" + chave
    _, gravado = _saida(["dconf", "read", caminho]) if shutil.which("dconf") else (1, "?")
    anotar("gsettings", receita=receita, esquema=esquema, chave=chave, valor=valor.strip(),
           padrao=gravado.strip() == "")


def antes_do_dconf(chave: str, receita: str = "") -> None:
    if not shutil.which("dconf"):
        return
    _, valor = _saida(["dconf", "read", chave])
    anotar("dconf", receita=receita, chave=chave, valor=valor.strip())


def antes_do_xfconf(canal: str, chave: str, tipo: str = "string", receita: str = "") -> None:
    if not shutil.which("xfconf-query"):
        return
    codigo, valor = _saida(["xfconf-query", "-c", canal, "-p", chave])
    # canal sem nenhuma propriedade ainda: o desfazer apaga o arquivo que sobrar vazio
    _, lista = _saida(["xfconf-query", "-c", canal, "-l"])
    anotar("xfconf", receita=receita, canal=canal, chave=chave, existia=codigo == 0,
           valor=valor, tipo_valor=tipo, canal_existia=any(l.startswith("/") for l in lista.splitlines()))


def antes_do_processo(nome: str, receita: str = "") -> None:
    codigo, _ = _saida(["pgrep", "-x", nome])
    anotar("processo", receita=receita, nome=nome, rodava=codigo == 0)


def main(argumentos: list[str]) -> int:
    """Chamado pelas funcoes d3_* dos scripts. Nunca falha o script por anotar."""
    if os.environ.get("D3_SEM_DIARIO") or os.environ.get("CTX_SEM_DIARIO"):
        return 0
    receita = os.environ.get("D3_RECEITA") or os.environ.get("CTX_RECEITA", "")
    try:
        comando, *resto = argumentos
        if comando == "antes":
            for caminho in resto:
                antes_do_caminho(Path(caminho), receita)
        elif comando == "gsettings":
            antes_do_gsettings(resto[0], resto[1], receita)
        elif comando == "dconf":
            antes_do_dconf(resto[0], receita)
        elif comando == "xfconf":
            antes_do_xfconf(resto[0], resto[1], resto[2] if len(resto) > 2 else "string", receita)
        elif comando == "processo":
            antes_do_processo(resto[0], receita)
        elif comando == "pasta":
            for caminho in resto:
                pasta = Path(caminho).expanduser()
                if not pasta.exists():
                    anotar("pasta", receita=receita, caminho=str(pasta))
        elif comando == "criado":
            for caminho in resto:
                anotar("criado", receita=receita, caminho=str(Path(caminho).expanduser()))
        elif comando == "pacotes" and resto:
            anotar("pacotes", receita=receita, nomes=list(resto))
    except (ValueError, IndexError, OSError) as erro:
        estado.registrar(f"diario: nao consegui anotar {argumentos}: {erro}")
    return 0


# roda como root numa copia que e do root: link que aponta para fora da propria
# arvore (absoluto, ou com .. demais) sai, para nao levar ao sistema um atalho
# para a pasta da pessoa
LINKS_PY = """import os, sys
raiz = os.path.realpath(sys.argv[1])
for pasta, dirs, arqs in os.walk(raiz):
    for nome in dirs + arqs:
        caminho = os.path.join(pasta, nome)
        if os.path.islink(caminho):
            alvo = os.path.realpath(caminho)
            if alvo != raiz and not alvo.startswith(raiz + os.sep):
                os.unlink(caminho)
"""

# posto no comeco de todo script de receita pelo motor
FUNCOES_SHELL = r'''
_d3_diario() { PYTHONPATH="$D3_DIARIO_PAI${PYTHONPATH:+:$PYTHONPATH}" "$D3_DIARIO_PYTHON" -m "$D3_DIARIO_PACOTE.diario" "$@" || true; }
d3_antes() { _d3_diario antes "$@"; }
d3_gsettings() { _d3_diario gsettings "$@"; }
d3_dconf() { _d3_diario dconf "$@"; }
d3_xfconf() { _d3_diario xfconf "$@"; }
d3_processo() { _d3_diario processo "$@"; }
d3_criado() { _d3_diario criado "$@"; }
# pasta comum (~/.themes, ~/.icons...) que ainda nao existe: o desfazer tira se ficar vazia
d3_pasta() { _d3_diario pasta "$@"; }
# antes e depois de um instalador de terceiros: o que o padrao (glob) casar e nao
# existia antes entra no diario como criado
_D3_ANTES=""
d3_antes_de() {
  _D3_ANTES="$(for g in "$@"; do compgen -G "$g" || true; done)"
  local e
  while IFS= read -r e; do [ -n "$e" ] && d3_antes "$e"; done <<< "$_D3_ANTES"
  return 0
}
d3_depois_de() {
  local g e
  for g in "$@"; do
    while IFS= read -r e; do
      [ -n "$e" ] || continue
      grep -qxF -- "$e" <<< "$_D3_ANTES" || d3_criado "$e"
    done < <(compgen -G "$g" || true)
  done
  return 0
}
d3_pacotes() { _d3_diario pacotes "$@"; }
# ORIGEM (arquivo ou pasta da pessoa) vai para DESTINO no sistema como root:root,
# sem escrita para grupo e outros, e opcionalmente com MODO (arquivo). O root
# copia antes para uma pasta nova dele (sudo mktemp -d) e instala de la: link
# simbolico na raiz da origem e recusado, e o que aponta para fora da arvore sai.
# Trecho que chama isto conta como trecho com sudo (motor.py): nada de codigo
# de terceiros nele.
d3_raiz_instalar() {
  local origem=$1 destino=$2 modo=${3:-} r
  if [ -L "$origem" ] || [ ! -e "$origem" ]; then
    echo "recusado (link simbolico ou ausente): $origem" >&2; return 1
  fi
  r="$(sudo -n mktemp -d)" || return 1
  if ! sudo -n cp -R -P --no-preserve=all -- "$origem" "$r/c" || sudo -n test -L "$r/c"; then
    sudo -n rm -rf -- "$r"; echo "recusado: $origem" >&2; return 1
  fi
  sudo -n python3 -I -c "$D3_LINKS_PY" "$r/c"
  sudo -n chown -R root:root "$r/c"
  sudo -n chmod -R u+rwX,go+rX,go-w "$r/c"
  if [ -n "$modo" ]; then sudo -n chmod "$modo" "$r/c"; fi
  sudo -n install -d -m 755 -- "$(dirname "$destino")"
  sudo -n rm -rf -- "$destino"
  if ! sudo -n mv -T -- "$r/c" "$destino"; then
    sudo -n rm -rf -- "$r"; return 1
  fi
  sudo -n rm -rf -- "$r"
}
'''


def ambiente_shell(receita: str, anotar_ligado: bool) -> dict[str, str]:
    """Variaveis que as FUNCOES_SHELL usam para achar este modulo."""
    return {
        "D3_DIARIO_PAI": str(caminhos.PACOTE.parent),
        "D3_DIARIO_PACOTE": caminhos.PACOTE.name,
        "D3_DIARIO_PYTHON": sys.executable or "python3",
        "D3_RECEITA": receita,
        "D3_LINKS_PY": LINKS_PY,
        **({} if anotar_ligado else {"D3_SEM_DIARIO": "1"}),
    }


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
