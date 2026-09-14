#!/bin/sh
# Carregado pelo ~/.xprofile: faz os programas GTK exportarem o menu para o painel.
case ":$GTK_MODULES:" in
  *:appmenu-gtk-module:*) ;;
  *) GTK_MODULES="${GTK_MODULES:+$GTK_MODULES:}appmenu-gtk-module"; export GTK_MODULES ;;
esac
export UBUNTU_MENUPROXY=1
