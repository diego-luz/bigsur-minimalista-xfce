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
    # impressao digital da chave da Microsoft; outra chave no endereco e recusada
    impressao="BC528686B50D79E339D3721CEB3E94ADBE1229CF"
    origem="packages.microsoft.com"
    pacotes="code"
    ;;
  docker)
    # o mesmo repositorio que o get.docker.com configura, sem rodar script de fora
    url_chave="https://download.docker.com/linux/debian/gpg"
    chaveiro="/usr/share/keyrings/docker.gpg"
    lista="/etc/apt/sources.list.d/docker.list"
    versao="$(. /etc/os-release && echo "$VERSION_CODENAME")"
    linha="deb [arch=$(dpkg --print-architecture) signed-by=$chaveiro] https://download.docker.com/linux/debian $versao stable"
    impressao="9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
    origem="download.docker.com"
    pacotes="docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras"
    ;;
  *)
    echo "fonte desconhecida: $fonte" >&2
    exit 2
    ;;
esac
# o repositorio de fora so serve os pacotes dele: nao pode trocar outros do
# Debian (prioridade 100 para o resto, abaixo dos 500 do Debian)
preferencias="/etc/apt/preferences.d/$fonte"

# sem o gpg nao da para conferir o dono da chave: entao nada entra no apt
command -v gpg >/dev/null || { echo "gpg ausente: nao da para conferir a chave; nada foi acrescentado" >&2; exit 1; }
tmp="$(mktemp)"
gpg_casa="$(mktemp -d)"
trap 'rm -rf "$tmp" "$gpg_casa"' EXIT
impressao_de() {
  GNUPGHOME="$gpg_casa" gpg --show-keys --with-colons "$1" 2>/dev/null | awk -F: '/^fpr/{print $10; exit}'
}

if [ -f "$chaveiro" ] && [ -f "$lista" ]; then
  # a que ja estava tambem precisa ser a esperada
  achada="$(impressao_de "$chaveiro")"
  if [ "$achada" != "$impressao" ]; then
    echo "a chave em $chaveiro nao e a esperada (${achada:-ilegivel}); confira antes de continuar" >&2
    exit 1
  fi
  echo "a fonte $fonte ja estava configurada"
else
  echo "baixando a chave de $url_chave"
  curl -fsSL --max-time 40 "$url_chave" -o "$tmp"
  [ -s "$tmp" ] || { echo "a chave veio vazia" >&2; exit 1; }
  achada="$(impressao_de "$tmp")"
  if [ "$achada" != "$impressao" ]; then
    echo "a chave de $fonte nao e a esperada (${achada:-ilegivel}); nada foi acrescentado ao apt" >&2
    exit 1
  fi

  # guarda a chave em chaveiro proprio e amarra a fonte a ela com signed-by,
  # para que esta chave nao valide nenhum outro repositorio do sistema
  gpg --dearmor --yes --output "$chaveiro" < "$tmp"
  chmod 0644 "$chaveiro"

  printf '%s\n' "$linha" > "$lista"
  chmod 0644 "$lista"
  echo "fonte adicionada em $lista"
fi

if [ ! -f "$preferencias" ]; then
  {
    printf 'Package: *\nPin: origin %s\nPin-Priority: 100\n\n' "$origem"
    printf 'Package: %s\nPin: origin %s\nPin-Priority: 500\n' "$pacotes" "$origem"
  } > "$preferencias"
  chmod 0644 "$preferencias"
  echo "a fonte so serve: $pacotes ($preferencias)"
fi

echo "atualizando o indice apenas desta fonte"
apt-get update -o Dir::Etc::sourcelist="$lista" \
               -o Dir::Etc::sourceparts="-" \
               -o APT::Get::List-Cleanup="0"
echo "pronto"
