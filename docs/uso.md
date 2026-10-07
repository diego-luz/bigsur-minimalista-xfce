# Usando o d3bian-init-bigsur-minimalista-xfce

[← voltar ao README](../README.md)

## Rodar

Clone com o nome da pasta igual ao do pacote Python (com `_`) e rode como módulo:

```sh
git clone https://git.saberdl.dev.br/d3bian-temas/bigsur-minimalista-xfce.git d3bian_init_bigsur_minimalista_xfce
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
são quatro pacotes a menos e nenhum processo permanente além do painel. Quem
quiser pode ligar a barra em ilhas (com um dock) e os efeitos do picom, opções
que vêm desligadas.

O completo é o [bigsur-xfce](https://git.saberdl.dev.br/d3bian-temas/bigsur-xfce).

## Opções

| Opção | Valores |
|---|---|
| `tema` | claro, escuro |
| `destaque` (cor dos botões e da seleção) | padrão, azul, roxo, rosa, vermelho, laranja, amarelo, verde, cinza |
| `logo` do canto | Debian, Debian magenta, Tux, Tux colorido |
| `janelas` (encaixe e bordas) | sim, não |
| `ilhas` (barra em ilhas) | não, sim |
| `efeitos` (picom) | desligados, só sombras e cantos, desfoque e sombras |
| `papel_de_parede` | do tema, manter o atual, ou um da galeria |
| `login_fundo` | o do desktop, do tema, ou um da galeria |
| `login_desfoque` | sim, não |
| `login_usuarios` | nome e senha, lista |
| `bloqueio` de tela | nunca, 5, 10, 15, 30 minutos |

Os padrões deixam o minimalista de sempre: barra única no topo e efeitos
desligados. As ilhas e o picom vêm do
[oasis-xfce](https://git.saberdl.dev.br/d3bian-temas/oasis-xfce).

## Barra em ilhas

Com `ilhas = sim`, a barra do topo solta da borda e ganha cantos redondos, e as
janelas abertas vão para um dock (o `xfce4-docklike-plugin`) numa ilha no meio,
embaixo, com alguns programas fixados (arquivos, terminal, navegador, editor de
texto). O fundo das ilhas segue o tema, um pouco translúcido, e o indicador do
dock usa a cor de destaque.

As ilhas entram pelo `xfce4-panel-profiles load`. Painel solto não reserva
espaço na tela, então o projeto põe margens no xfwm4 (Ajustes do gerenciador de
janelas, ajustes finos, Espaços de trabalho, Margens), só depois que o `load` deu
certo: as janelas maximizadas param antes das ilhas, e o encaixe também. As
margens são em pixels de verdade: com a escala 2 do Xfce (telas HiDPI), elas
saem dobradas. As posições são calculadas para o monitor principal e a escala de
agora: mudou a resolução ou a escala, rode de novo só a barra:

```sh
python3 -m d3bian_init_bigsur_minimalista_xfce aplicar --apenas painel
```

Voltando para a barra única, as margens que as ilhas puseram saem (margem que
você mudou depois fica).

## Efeitos (picom)

Com `efeitos` em **só sombras** ou **desfoque**, o picom desenha sombras e cantos
redondos nas janelas (e, com desfoque, o fundo atrás do que é translúcido fica
embaçado). Com o picom ligado, o compositor do próprio xfwm4 fica desligado (os
dois juntos brigam pela tela) e o picom inicia junto com a sessão
(`~/.config/autostart/d3bian-minimalista-picom.desktop`, que chama o
`~/.local/bin/d3bian-picom`). Antes de escrever o `picom.conf`, o projeto confere
o vídeo: com `glxinfo` dizendo `llvmpipe` (ou sem renderização direta), numa
placa de vídeo de VM sem 3D, ou numa VM sem como confirmar, o picom roda
**leve**: `xrender`, sem desfoque e sem vsync. Se o picom não ficar de pé (agora
ou ao entrar na sessão), o `d3bian-picom` liga de volta o compositor do xfwm4.
Com os efeitos **desligados**, o picom deste projeto para e o compositor do xfwm4
volta ao que era antes de o picom ligar. Um picom que você mesmo abriu, com
outra configuração, nunca é fechado pelo projeto.

## Encaixe de janelas

Com `janelas = sim`: Super e as setas para metades e maximizar, Super+1 a 4 para
os quartos (do próprio xfwm4), Super+C centraliza, Super+X ocupa quase a tela
toda, Super+Shift e as setas dividem em terços e Super+Z abre um quadro de
layouts. Arrastar a janela até a borda também encaixa. O `d3bian-janelas` e o
`d3bian-layouts` descontam as margens do xfwm4, então com as ilhas nada fica por
baixo delas. Os atalhos levam o caminho entre aspas, para a pasta pessoal com
espaço.

## O que fica onde

Configuração, estado, cópias de segurança e downloads ficam em
`~/.config/d3bian-init-bigsur-minimalista`, `~/.local/state/d3bian-init-bigsur-minimalista`
e `~/.local/share/d3bian-init-bigsur-minimalista`, separados do bigsur completo; a tela
de login também tem nomes próprios (`/usr/share/themes/d3bian-login-minimalista`,
`/etc/lightdm/lightdm.conf.d/91-d3bian-minimalista.conf`) — os dois podem conviver na
mesma máquina.

| Caminho | Escrito por |
|---|---|
| `~/.local/state/d3bian-init-bigsur-minimalista/painel-ilhas.tar.bz2` | o perfil das ilhas, carregado pelo `xfce4-panel-profiles` |
| `~/.config/picom/picom.conf`, `~/.config/autostart/d3bian-minimalista-picom.desktop`, `~/.local/bin/d3bian-picom` | efeitos |
| `~/.local/bin/d3bian-janelas`, `d3bian-layouts`, `d3bian-bordas` | encaixe, layouts e bordas de janela |
| `~/.gtkrc-2.0` | tema dos programas GTK 2, num bloco marcado |

## Sistemas

Família Debian (a verificação aceita `debian` no `ID` ou no `ID_LIKE` do
`/etc/os-release`), numa sessão gráfica do Xfce com o `xfconf-query`. Antes de
instalar, o painel confere também a permissão de administrador, o espaço em disco
e o acesso aos repositórios.

## Voltar ao que era antes

Em Aparência, **Voltar ao que era antes**, ou `restaurar --sim`. A barra volta pelo
`xfce4-panel-profiles` e o diário de alterações desfaz o resto. Com **Remover também o
que foi instalado** saem os pacotes que o projeto instalou.

O picom deste projeto para, e o compositor do xfwm4, as margens e a sombra dos
painéis voltam pelo diário. O `~/.gtkrc-2.0` perde o bloco marcado (e some, se
só existia pelo projeto).
