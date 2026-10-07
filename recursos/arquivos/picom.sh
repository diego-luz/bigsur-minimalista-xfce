#!/bin/sh
# O picom do projeto (o mesmo do d3bian-init-oasis-xfce), iniciado junto com
# a sessao.
#
#   d3bian-picom           inicia o picom com ~/.config/picom/picom.conf e fica
#                          esperando; se ele sair com erro e a tela continuar
#                          de pe, o compositor do xfwm4 volta
#   d3bian-picom parar     para so este picom; um picom aberto por conta
#                          propria, com outra configuracao, fica
#   d3bian-picom rodando   sai com 0 se este picom esta rodando
#
# O que e "este picom" sai da linha de comando exata, lida do /proc: nada de
# expressao regular sobre um caminho que pode ter espaco.
conf="$HOME/.config/picom/picom.conf"
eu="$HOME/.local/bin/d3bian-picom"

ajuda() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; }

procurar() {  # procurar ARG... : pids desta conta com exatamente esses argumentos
  alvo=$(printf '%s\n' "$@")
  for d in /proc/[0-9]*; do
    [ -O "$d" ] || continue
    linha=$(tr '\0' '\n' < "$d/cmdline" 2>/dev/null) || continue
    if [ "$linha" = "$alvo" ]; then echo "${d#/proc/}"; fi
  done
}

nosso() { procurar picom --config "$conf"; }

case "${1:-}" in
  parar)
    # primeiro quem espera, para ele nao achar que o picom caiu e religar o xfwm4
    for p in $(procurar /bin/sh "$eu") $(nosso); do kill "$p" 2>/dev/null || true; done
    # o xfwm4 nao liga o compositor dele enquanto o picom nao sai de vez
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      [ -z "$(nosso)" ] && exit 0
      sleep 0.5
    done
    exit 0 ;;
  rodando)
    [ -n "$(nosso)" ]
    exit ;;
  "") ;;
  *) ajuda; exit 1 ;;
esac

# sem o picom, ou com outro compositor ja de pe, vale o do xfwm4
volta_xfwm4() {
  # na saida da sessao a tela ja foi embora: ai nao se mexe em nada
  if xprop -root _NET_SUPPORTING_WM_CHECK >/dev/null 2>&1; then
    xfconf-query -c xfwm4 -p /general/use_compositing -s true 2>/dev/null || true
    echo "d3bian-picom: o picom saiu com erro ($1); o compositor do xfwm4 voltou" >&2
  fi
}

[ -n "$(nosso)" ] && exit 0
command -v picom >/dev/null || { volta_xfwm4 "picom ausente"; exit 1; }
picom --config "$conf" &
wait $!
codigo=$?
[ "$codigo" -eq 0 ] || volta_xfwm4 "codigo $codigo"
exit "$codigo"
