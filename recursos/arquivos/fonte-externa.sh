#!/usr/bin/env bash
# Habilita uma fonte de pacotes que nao e do Debian.
#
#   fonte-externa.sh microsoft-vscode
#
# Cada fonte e descrita aqui dentro, e nao vem de fora, para que o que o
# programa pode acrescentar ao seu apt esteja tudo em um arquivo so, legivel.
# Roda como root.
set -euo pipefail

fonte="${1:-}"

case "$fonte" in
  microsoft-vscode)
    url_chave="https://packages.microsoft.com/keys/microsoft.asc"
    chaveiro="/usr/share/keyrings/microsoft-vscode.gpg"
    lista="/etc/apt/sources.list.d/microsoft-vscode.list"
    linha="deb [arch=amd64,arm64,armhf signed-by=$chaveiro] https://packages.microsoft.com/repos/code stable main"
    ;;
  docker)
    # o mesmo repositorio que o get.docker.com configura, sem rodar script de fora
    url_chave="https://download.docker.com/linux/debian/gpg"
    chaveiro="/usr/share/keyrings/docker.gpg"
    lista="/etc/apt/sources.list.d/docker.list"
    versao="$(. /etc/os-release && echo "$VERSION_CODENAME")"
    linha="deb [arch=$(dpkg --print-architecture) signed-by=$chaveiro] https://download.docker.com/linux/debian $versao stable"
    ;;
  *)
    echo "fonte desconhecida: $fonte" >&2
    exit 2
    ;;
esac

if [ -f "$chaveiro" ] && [ -f "$lista" ]; then
  echo "a fonte $fonte ja estava configurada"
else
  echo "baixando a chave de $url_chave"
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  curl -fsSL --max-time 40 "$url_chave" -o "$tmp"
  [ -s "$tmp" ] || { echo "a chave veio vazia" >&2; exit 1; }

  # guarda a chave em chaveiro proprio e amarra a fonte a ela com signed-by,
  # para que esta chave nao valide nenhum outro repositorio do sistema
  gpg --dearmor --yes --output "$chaveiro" < "$tmp"
  chmod 0644 "$chaveiro"

  printf '%s\n' "$linha" > "$lista"
  chmod 0644 "$lista"
  echo "fonte adicionada em $lista"
fi

echo "atualizando o indice apenas desta fonte"
apt-get update -o Dir::Etc::sourcelist="$lista" \
               -o Dir::Etc::sourceparts="-" \
               -o APT::Get::List-Cleanup="0"
echo "pronto"
