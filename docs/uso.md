# Usando o d3bian-init-bigsur-minimalista-xfce

[← voltar ao README](../README.md)

## Rodar

Clone com o nome da pasta igual ao do pacote Python (com `_`) e rode como módulo:

```sh
git clone https://git.saberdl.dev.br/d3bian/bigsur-minimalista-xfce.git d3bian_init_bigsur_minimalista_xfce
python3 -m d3bian_init_bigsur_minimalista_xfce            # pede a senha uma vez e abre o painel
python3 -m d3bian_init_bigsur_minimalista_xfce aplicar --simular
```

O painel abre em `http://127.0.0.1:8974`.

## Instalação pelo painel

1. `python3 -m d3bian_init_bigsur_minimalista_xfce` abre a página no navegador (pede a senha de administrador uma vez, no terminal).
2. Em **Aparência**, escolha as opções e clique em **Instalar tudo**; o progresso de cada etapa aparece na hora.
3. Depois, mudar uma opção e **Aplicar** roda de novo só as etapas afetadas.
4. **Voltar ao que era antes** desfaz tudo; com **Remover também o que foi instalado**, tira também os pacotes.

A tela **Programas úteis** traz uma lista pronta de programas do repositório
oficial do Debian, separados por categoria, mostrando só o que serve para o
hardware encontrado. Marque e instale de uma vez.

## O que muda em relação ao bigsur completo

| Sai | Fica |
|---|---|
| Dock inferior (Plank) | Barra única no topo, com menu, bandeja, som, bateria, relógio e sair |
| Barra de menus global do programa ativo | Tema WhiteSur **sólido**, sem transparência (`install.sh -o solid`) |
| Widget de relógio e de anéis (Conky) | Ícones e cursores WhiteSur |
| Lançador estilo Spotlight (rofi) | Encaixe de janelas por atalho |
| Sombras e cantos arredondados (picom) | Tela de login e bloqueio combinando |
| Tema do Firefox | Papéis de parede do WhiteSur, ou o seu |

Sem dock, sem compositor extra e sem Conky, o desktop também pesa menos:
são quatro pacotes a menos e nenhum processo permanente além do painel.

O completo é o [bigsur-xfce](https://git.saberdl.dev.br/d3bian/bigsur-xfce).

## Opções

`tema` (claro/escuro), `destaque`, `logo` do canto, `janelas` (encaixe),
`papel_de_parede`, `login_fundo`, `login_desfoque`,
`login_usuarios` e `bloqueio` de tela.

## O que fica onde

Configuração, estado e cópias de segurança ficam em
`~/.config/d3bian-init-bigsur-minimalista` e `~/.local/state/d3bian-init-bigsur-minimalista`,
separados do bigsur completo — os dois podem conviver na mesma máquina.

## Sistemas

Família Debian (a verificação aceita `debian` no `ID` ou no `ID_LIKE` do
`/etc/os-release`), numa sessão gráfica do Xfce com o `xfconf-query`. Antes de
instalar, o painel confere também a permissão de administrador, o espaço em disco
e o acesso aos repositórios.

## Voltar ao que era antes

Em Aparência, **Voltar ao que era antes**, ou `restaurar --sim`. A barra volta pelo
`xfce4-panel-profiles` e o diário de alterações desfaz o resto. Com **Remover também o
que foi instalado** saem os pacotes que o projeto instalou.
