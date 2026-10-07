#!/usr/bin/env bash
# Faz do Flameshot o capturador padrao: abre com a sessao e atende o Print Screen.
#
# Roda como o usuario, depois do apt. Nada aqui aponta para a pasta do
# programa: a instalacao vem de um pendrive, e o que a sessao le fica na maquina.
#
# O Print Screen chama ~/.local/bin/d3bian-captura, e nao o flameshot direto.
# Se o Flameshot for removido pela tela de Programas, a tecla volta sozinha ao
# capturador do XFCE em vez de chamar um programa que nao existe mais.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "rode como usuario comum, nao como root" >&2
  exit 1
fi
if ! command -v flameshot >/dev/null; then
  echo "flameshot ausente: o apt nao o instalou" >&2
  exit 1
fi

# o que muda aqui entra no diario do projeto, como nas receitas: o "Voltar ao
# que era antes" devolve o atalho, o autostart e o flameshot.ini. Este arquivo
# fica em <pacote>/recursos/arquivos
pacote=$(cd "$(dirname "$0")/../.." && pwd)
anotar() {
  PYTHONPATH="$(dirname "$pacote")${PYTHONPATH:+:$PYTHONPATH}" D3_RECEITA=programas \
    python3 -m "$(basename "$pacote").diario" "$@" >/dev/null 2>&1 || true
}

# o comando do atalho passa pelo g_shell_parse_argv: o caminho vai entre
# aspas simples, para a pasta pessoal com espaco
q() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

echo "criando o atalho de captura"
mkdir -p "$HOME/.local/bin"
anotar antes "$HOME/.local/bin/d3bian-captura"
cat > "$HOME/.local/bin/d3bian-captura" <<'FIM'
#!/bin/sh
# Print Screen: o Flameshot quando instalado, senao o capturador do XFCE
if command -v flameshot >/dev/null 2>&1; then
  exec flameshot gui
fi
exec xfce4-screenshooter "$@"
FIM
chmod +x "$HOME/.local/bin/d3bian-captura"

echo "Print Screen passa a abrir o Flameshot"
anotar xfconf xfce4-keyboard-shortcuts /commands/custom/Print string
xfconf-query -c xfce4-keyboard-shortcuts -p "/commands/custom/Print" \
  -n -t string -s "$(q "$HOME/.local/bin/d3bian-captura")" 2>/dev/null \
  || xfconf-query -c xfce4-keyboard-shortcuts -p "/commands/custom/Print" \
       -s "$(q "$HOME/.local/bin/d3bian-captura")"

# O mesmo nome e conteudo que o proprio Flameshot grava quando se marca
# "Iniciar com o sistema" nas configuracoes dele; assim a caixinha de la
# continua mandando neste arquivo. TryExec faz a sessao pular a entrada se o
# programa for removido.
echo "abrindo o Flameshot junto com a sessao"
mkdir -p "$HOME/.config/autostart"
anotar antes "$HOME/.config/autostart/Flameshot.desktop"
cat > "$HOME/.config/autostart/Flameshot.desktop" <<'FIM'
[Desktop Entry]
Name=flameshot
Icon=flameshot
Exec=flameshot
TryExec=flameshot
Terminal=false
Type=Application
X-GNOME-Autostart-enabled=true
FIM

# startupLaunch acompanha o autostart acima; o aviso de "ja esta rodando" a
# cada inicio so atrapalha quando ele abre sozinho
ini="$HOME/.config/flameshot/flameshot.ini"
anotar pasta "$(dirname "$ini")"
anotar antes "$ini"
mkdir -p "$(dirname "$ini")"
[ -f "$ini" ] || printf '[General]\n' > "$ini"
grep -q '^\[General\]' "$ini" || printf '[General]\n' >> "$ini"
ini_chave() {
  if grep -q "^$1=" "$ini"; then
    sed -i "s|^$1=.*|$1=$2|" "$ini"
  else
    sed -i "/^\[General\]/a $1=$2" "$ini"
  fi
}
ini_chave startupLaunch true
ini_chave showStartupLaunchMessage false

# ja deixa rodando nesta sessao, sem esperar o proximo login
if [ -n "${DISPLAY:-}" ] && ! pgrep -u "$(id -u)" -x flameshot >/dev/null; then
  anotar processo flameshot
  setsid -f flameshot >/dev/null 2>&1 </dev/null || true
fi

echo "Flameshot pronto: Print Screen abre a selecao de area"
