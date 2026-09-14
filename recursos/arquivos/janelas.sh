#!/usr/bin/env bash
# Posiciona a janela ativa em fracoes da tela.
#
# O xfwm4 ja faz metades e quartos sozinho, e os atalhos usam isso. Este script
# cobre o que ele nao faz: centralizar e dividir em tercos.
#
#   bigsur-janelas centro          centraliza ocupando 72% da tela
#   bigsur-janelas quase-cheia     ocupa 92%, com respiro nas bordas
#   bigsur-janelas 2-3-esquerda    dois tercos a esquerda
#   bigsur-janelas 1-3-direita     um terco a direita
#   bigsur-janelas 2-3-direita     dois tercos a direita
#   bigsur-janelas 1-3-esquerda    um terco a esquerda
set -u

comando="${1:-}"
[ -z "$comando" ] && { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

for exigido in wmctrl xprop; do
  command -v "$exigido" >/dev/null || { echo "falta o $exigido: sudo apt install wmctrl x11-utils"; exit 1; }
done

# Area util: a tela menos o painel e o dock. Vem em x, y, largura, altura.
leia_area(){
  local bruto
  bruto="$(xprop -root -notype _NET_WORKAREA 2>/dev/null | sed 's/.*= //;s/,//g')"
  # shellcheck disable=SC2086
  set -- $bruto
  AX="${1:-0}"; AY="${2:-0}"; AW="${3:-0}"; AH="${4:-0}"
  [ "${AW:-0}" -gt 0 ] || { echo "nao consegui ler a area util da tela"; exit 1; }
}

# A moldura da janela entra na conta, senao ela passa da borda.
leia_moldura(){
  local bruto
  bruto="$(xprop -id "$(xdotool getactivewindow 2>/dev/null)" -notype _NET_FRAME_EXTENTS 2>/dev/null | sed 's/.*= //;s/,//g')"
  # shellcheck disable=SC2086
  set -- $bruto
  ME="${1:-0}"; MD="${2:-0}"; MC="${3:-0}"; MB="${4:-0}"
  case "$ME$MD$MC$MB" in *[!0-9]*|"") ME=0; MD=0; MC=0; MB=0 ;; esac
}

posicionar(){ # posicionar <x> <y> <largura> <altura>
  local x="$1" y="$2" w="$3" h="$4"
  wmctrl -r :ACTIVE: -b remove,maximized_vert,maximized_horz 2>/dev/null
  sleep 0.08
  leia_moldura
  # wmctrl mede o conteudo, nao a moldura; descontamos as bordas
  w=$(( w - ME - MD )); h=$(( h - MC - MB ))
  [ "$w" -lt 200 ] && w=200
  [ "$h" -lt 150 ] && h=150
  wmctrl -r :ACTIVE: -e "0,$x,$y,$w,$h"
}

leia_area

case "$comando" in
  centro)
    w=$(( AW * 72 / 100 )); h=$(( AH * 78 / 100 ))
    posicionar $(( AX + (AW - w) / 2 )) $(( AY + (AH - h) / 2 )) "$w" "$h" ;;
  quase-cheia)
    w=$(( AW * 92 / 100 )); h=$(( AH * 92 / 100 ))
    posicionar $(( AX + (AW - w) / 2 )) $(( AY + (AH - h) / 2 )) "$w" "$h" ;;
  2-3-esquerda) posicionar "$AX" "$AY" $(( AW * 2 / 3 )) "$AH" ;;
  1-3-direita)  posicionar $(( AX + AW * 2 / 3 )) "$AY" $(( AW / 3 )) "$AH" ;;
  2-3-direita)  posicionar $(( AX + AW / 3 )) "$AY" $(( AW * 2 / 3 )) "$AH" ;;
  1-3-esquerda) posicionar "$AX" "$AY" $(( AW / 3 )) "$AH" ;;
  *) echo "comando desconhecido: $comando"; sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
