# Desenvolvimento

[← voltar ao README](../README.md)

Painel em Python puro (só a biblioteca padrão) com HTML/JS sem dependências.
Cada etapa é uma receita em TOML (`recursos/receitas`), executada pelo `motor.py`;
o `diario.py` anota cada mudança e o `desfazer.py` usa essas anotações para
voltar ao que era antes.

## Receitas

| id | nome |
|---|---|
| 00 | cópia de segurança do que existe hoje |
| 10 | pacotes do repositório Debian |
| 20 | fontes de interface e monoespaçada |
| 30 | tema WhiteSur das janelas (variante sólida) |
| 31 | ícones WhiteSur |
| 32 | cursores WhiteSur |
| 33 | papéis de parede |
| 34 | tema nos programas Qt |
| 38 | barra única do topo |
| 40 | tema, fontes, botões e papel de parede |
| 42 | cores do terminal |
| 43 | atalhos de teclado |
| 44 | encaixe de janelas |
| 97 | tela de login |
| 98 | bloqueio de tela |

## Imagens de exemplo

As prévias de `recursos/web/exemplos` e `recursos/web/capturas` são simulações
desenhadas em HTML e fotografadas pelo chromium pelo
`ferramentas/gerar_exemplos.py`: papel de parede, a barra única do topo e uma
janela, com as cores aproximadas do WhiteSur sólido. Nada da máquina de quem gera
entra nelas. Quem quiser a tela de verdade usa o botão **Capturar a tela como
está** na própria página (ou `capturar` na linha de comando), que troca estas.

```sh
python3 ferramentas/gerar_exemplos.py
```

Precisa de chromium e ImageMagick.

As miniaturas de `recursos/web/papeis` saem do repositório de papéis do WhiteSur,
baixado pela receita 33. Para refazer depois de baixar uma versão nova:

```sh
for f in ~/.local/share/backgrounds/WhiteSur/*; do
  convert "$f" -resize 320x -strip -quality 78 \
    "recursos/web/papeis/$(basename "${f%.*}").jpg"
done
```
