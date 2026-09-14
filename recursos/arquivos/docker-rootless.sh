#!/usr/bin/env bash
# Configura o Docker no modo rootless para o usuario que roda o painel.
#
# Roda como o usuario, e nao como root: o daemon rootless e dele. Os poucos
# passos de sistema usam sudo -n, com a autorizacao que o painel ja tem.
#
# O usuario nao entra no grupo docker. Esse grupo fala com o daemon de root e
# vale tanto quanto ser root, o que desfaria a vantagem do rootless.
set -euo pipefail

usuario="$(id -un)"
if [ "$(id -u)" -eq 0 ]; then
  echo "rode como usuario comum, nao como root" >&2
  exit 1
fi
if ! command -v dockerd-rootless-setuptool.sh >/dev/null; then
  echo "dockerd-rootless-setuptool.sh ausente: o docker-ce-rootless-extras nao foi instalado" >&2
  exit 1
fi

# o rootless mapeia os ids do container numa faixa reservada ao usuario
if ! grep -q "^$usuario:" /etc/subuid || ! grep -q "^$usuario:" /etc/subgid; then
  echo "reservando ids para $usuario em /etc/subuid e /etc/subgid"
  sudo -n usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$usuario"
fi

# Com o daemon de root ativo a ferramenta recusa continuar, e o rootless nao
# precisa dele. Fica instalado, so desligado
echo "desligando o daemon de root do Docker"
sudo -n systemctl disable --now docker.service docker.socket >/dev/null 2>&1 || true
sudo -n rm -f /var/run/docker.sock

echo "instalando o daemon rootless"
dockerd-rootless-setuptool.sh install

systemctl --user enable --now docker
# sem linger, o daemon para quando a sessao fecha
sudo -n loginctl enable-linger "$usuario"

# o setuptool cria o contexto rootless; usar ele dispensa DOCKER_HOST no shell
docker context use rootless >/dev/null

if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
  echo "Docker rootless ativo para $usuario"
else
  echo "o daemon rootless nao respondeu; veja: systemctl --user status docker" >&2
  exit 1
fi
