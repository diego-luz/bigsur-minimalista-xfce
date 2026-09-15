"""Painel web local.

Escuta so em 127.0.0.1. Ele executa coisas na maquina, entao nao deve ficar
acessivel pela rede. Quem quiser usar de outro computador que faca tunel SSH.
"""

from __future__ import annotations

import json
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import (caminhos, capturas, config, estado, papeis, programas,
               receitas, sistema)
from .tarefa import Tarefa

PORTA_PADRAO = 8730

TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".svg": "image/svg+xml",
    ".ico": "image/x-icon", ".woff2": "font/woff2",
}

tarefa = Tarefa()
parar = threading.Event()


class Painel(BaseHTTPRequestHandler):
    server_version = "d3bian-init-bigsur-xfce"

    def log_message(self, *_a) -> None:
        pass

    # ---- respostas -------------------------------------------------------
    def _envia(self, codigo: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(corpo)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, dados: dict, codigo: int = 200) -> None:
        self._envia(codigo, json.dumps(dados, ensure_ascii=False).encode(),
                    "application/json; charset=utf-8")

    def corpo(self) -> dict:
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if tamanho <= 0 or tamanho > 64_000:
            return {}
        try:
            dados = json.loads(self.rfile.read(tamanho))
        except (json.JSONDecodeError, OSError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def arquivo(self, alvo: Path) -> None:
        if not alvo.is_file():
            self._envia(404, b"nao encontrado", "text/plain; charset=utf-8")
            return
        self._envia(200, alvo.read_bytes(),
                    TIPOS.get(alvo.suffix.lower(), "application/octet-stream"))

    # ---- GET -------------------------------------------------------------
    def do_GET(self) -> None:
        rota = self.path.split("?")[0]
        if rota == "/":
            rota = "/index.html"

        if rota == "/api/estado":
            lista = receitas.carregar()
            self.json({
                "config": config.ler(),
                "opcoes": [o.como_dict() for o in config.OPCOES],
                "receitas": [r.como_dict() for r in lista],
                "instalado": receitas.instalado(lista),
                "previa": capturas.nome_do_momento(),
                # fotos tiradas nesta maquina; as outras sao os exemplos do pacote
                "proprias": sorted(p.stem for p in caminhos.CAPTURAS.glob("*.jpg")),
            })
            return

        if rota == "/api/verificacoes":
            lista = sistema.verificacoes()
            self.json({"verificacoes": lista, "impedimentos": sistema.impedimentos(lista)})
            return

        if rota == "/api/progresso":
            try:
                desde = int(self.path.split("desde=")[1].split("&")[0])
            except (IndexError, ValueError):
                desde = 0
            self.json(tarefa.instantaneo(desde))
            return

        if rota == "/api/programas":
            self.json(programas.com_estado())
            return

        if rota == "/api/papeis":
            atual = papeis.escolhido(config.ler())
            # o esquema da pagina precisa saber o que "do tema" escolheria
            do_tema = {t: (papeis.escolhido({"tema": t, "papel_de_parede": "do-tema"})
                           or Path("")).stem for t in ("escuro", "claro")}
            self.json({"papeis": papeis.disponiveis(), "doTema": do_tema,
                       "emUso": atual.stem if atual else ""})
            return


        if rota.startswith("/papeis/"):
            alvo = papeis.miniatura(Path(rota).stem)
            if alvo is None:
                self._envia(404, b"nao encontrado", "text/plain")
                return
            self.arquivo(alvo)
            return

        # previas: a captura do usuario tem prioridade sobre a do pacote
        if rota.startswith("/capturas/"):
            nome = Path(rota).stem
            if "/" in nome or ".." in nome:
                self._envia(404, b"nao encontrado", "text/plain")
                return
            self.arquivo(caminhos.captura(nome))
            return

        # os logos moram junto dos modelos, nao na pasta web
        if rota.startswith("/logos/"):
            nome = Path(rota).name
            if "/" in nome or ".." in nome or not nome.endswith(".svg"):
                self._envia(404, b"nao encontrado", "text/plain")
                return
            self.arquivo(caminhos.ARQUIVOS / "logos" / nome)
            return

        alvo = (caminhos.WEB / rota.lstrip("/")).resolve()
        if not str(alvo).startswith(str(caminhos.WEB.resolve())):
            self._envia(404, b"nao encontrado", "text/plain; charset=utf-8")
            return
        self.arquivo(alvo)

    # ---- POST ------------------------------------------------------------
    def do_POST(self) -> None:
        rota = self.path.split("?")[0]
        corpo = self.corpo()

        if rota == "/api/sair":
            self.json({"tchau": True})
            threading.Timer(0.4, parar.set).start()
            return

        if tarefa.ocupada() and rota != "/api/progresso":
            self.json({"iniciado": False, "motivo": "ocupado",
                       "detalhe": tarefa.rotulo}, 409)
            return

        if rota == "/api/aplicar":
            self._aplicar(corpo)
            return
        if rota == "/api/instalar":
            self._instalar_tudo(corpo)
            return
        if rota == "/api/programas/instalar":
            self._programas(corpo, remover=False)
            return
        if rota == "/api/programas/remover":
            self._programas(corpo, remover=True)
            return
        if rota == "/api/capturar":
            self._capturar(corpo)
            return
        if rota == "/api/reiniciar-login":
            self._reiniciar_login(corpo)
            return
        if rota == "/api/previa-login":
            # a previa usa as opcoes marcadas na pagina, mesmo antes de aplicar
            pedido = config.filtrar(corpo)
            iniciado = tarefa.funcao("Montando a previa da tela de login",
                                     lambda diz: capturas.previa_login(diz, pedido))
            self.json({"iniciado": iniciado}, 200 if iniciado else 409)
            return

        self._envia(404, b"nao encontrado", "text/plain; charset=utf-8")

    # ---- acoes -----------------------------------------------------------
    def _aplicar(self, corpo: dict) -> None:
        pedido = config.filtrar(corpo)
        if not pedido:
            self.json({"iniciado": False, "motivo": "nada valido"}, 400)
            return
        atual = config.ler()
        mudou = [c for c, v in pedido.items() if atual.get(c) != v]
        # sem diferenca, reaplica o conjunto: o botao sempre faz alguma coisa
        chaves = mudou or list(pedido)
        # receita que mudou depois de aplicada entra mesmo sem opcao alterada,
        # senao a nova tela de login nunca sairia do codigo
        pendentes = set(receitas.afetadas_por(list(pedido))) & receitas.desatualizadas()
        alvos = sorted(set(receitas.afetadas_por(chaves)) | pendentes,
                       key=lambda x: (len(x), x))
        if not alvos:
            self.json({"iniciado": False, "motivo": "nada a fazer"})
            return

        novidade = bool(mudou or pendentes)
        rotulo = ("Aplicando" if novidade else "Reaplicando") + ": " + ", ".join(alvos)
        iniciado = tarefa.funcao(
            rotulo,
            lambda diz: receitas.executar(apenas=alvos, refazer=True, saida=diz,
                                          cfg={**atual, **pedido}),
        )
        if not iniciado:
            self.json({"iniciado": False, "motivo": "ocupado"}, 409)
            return
        # so grava depois que a execucao comecou, senao a config passaria a
        # dizer que algo foi aplicado sem ter sido
        config.gravar(pedido)
        self.json({"iniciado": True, "receitas": alvos, "mudou": mudou,
                   "reaplicou": not novidade})

    def _reiniciar_login(self, corpo: dict) -> None:
        """Reinicia o LightDM, o que encerra a sessao grafica. Nunca sem confirmacao."""
        if corpo.get("confirmar") is not True:
            self.json({"iniciado": False, "motivo": "sem_confirmacao"}, 400)
            return
        try:
            instalada = "lightdm-gtk-greeter" in Path(
                "/etc/lightdm/lightdm.conf.d/90-d3bian.conf").read_text()
        except OSError:
            instalada = False
        if not instalada:
            # reiniciar antes de aplicar so fecharia a sessao para mostrar a tela antiga
            self.json({"iniciado": False, "motivo": "login_nao_aplicado"}, 412)
            return
        if not sistema.sudo_liberado():
            self.json({"iniciado": False, "motivo": "sem_permissao"}, 412)
            return
        self.json({"iniciado": True})
        estado.registrar("reiniciando o lightdm a pedido da pagina")
        # a resposta sai antes, porque a sessao e o navegador fecham junto. Sem
        # setsid: o sudo guarda a credencial por terminal, e o systemctl so
        # enfileira o reinicio, que continua mesmo com este processo morto
        threading.Timer(1.5, lambda: subprocess.Popen(
            ["sudo", "-n", "systemctl", "restart", "lightdm"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)).start()

    def _instalar_tudo(self, corpo: dict) -> None:
        impedem = sistema.impedimentos(sistema.verificacoes(usar_cache=False))
        if impedem:
            self.json({"iniciado": False, "motivo": "verificacoes",
                       "impedimentos": impedem}, 412)
            return
        pedido = config.filtrar(corpo)
        iniciado = tarefa.funcao(
            "Instalacao completa, pode levar de 15 a 25 minutos",
            lambda diz: receitas.executar(saida=diz, cfg={**config.ler(), **pedido}),
        )
        if not iniciado:
            self.json({"iniciado": False, "motivo": "ocupado"}, 409)
            return
        if pedido:
            config.gravar(pedido)
        self.json({"iniciado": True})

    def _programas(self, corpo: dict, remover: bool) -> None:
        try:
            escolhidos = programas.conferir(corpo.get("pacotes"))
        except programas.Recusado as erro:
            self.json({"iniciado": False, "erro": str(erro)}, 400)
            return
        externas = [] if remover else programas.fontes_necessarias(escolhidos)
        if externas and not corpo.get("confirmar_externo"):
            # nada e instalado antes de o usuario ver o que sera acrescentado
            # ao sistema; esta pergunta e separada da confirmacao de remocao
            self.json({"iniciado": False, "motivo": "fonte_externa",
                       "externas": externas})
            return

        if remover:
            extras = programas.arrastaria(escolhidos)
            if extras and not corpo.get("confirmar"):
                self.json({"iniciado": False, "motivo": "arrasta_outros",
                           "extras": extras})
                return
            comando = programas.comando_remover(escolhidos)
            rotulo = "Removendo: " + ", ".join(escolhidos)
            iniciado = tarefa.processo(rotulo, comando, root=True)
        else:
            rotulo = "Instalando: " + ", ".join(escolhidos)
            iniciado = tarefa.funcao(
                rotulo, lambda diz: programas.instalar(escolhidos, diz))
        self.json({"iniciado": iniciado, "pacotes": escolhidos,
                   "externas": [e["pkg"] for e in externas]})

    def _capturar(self, corpo: dict) -> None:
        modo = corpo.get("modo")
        espera = corpo.get("espera")
        espera = espera if isinstance(espera, int) and 0 <= espera <= 30 else 5
        if modo == "atual":
            alvo = lambda diz: capturas.capturar_atual(diz, espera)
        elif modo == "todas":
            alvo = lambda diz: capturas.capturar_todas(diz, espera)
        else:
            self.json({"iniciado": False, "erro": "modo invalido"}, 400)
            return
        self.json({"iniciado": tarefa.funcao(f"Capturando previas ({modo})", alvo)})


def subir(porta: int = PORTA_PADRAO, abrir: bool = True) -> int:
    caminhos.preparar()
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", porta), Painel)
    except OSError as erro:
        print(f"  nao consegui abrir a porta {porta}: {erro}")
        return 1
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    endereco = f"http://127.0.0.1:{porta}/"
    print(f"\n  d3bian-init-bigsur-xfce aberto em {endereco}")
    print("  Feche pelo botao na pagina, ou com Ctrl+C aqui.\n")
    if abrir:
        try:
            subprocess.Popen(["xdg-open", endereco],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            print("  abra o endereco acima no seu navegador")

    signal.signal(signal.SIGINT, lambda *_: parar.set())
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    while not parar.is_set():
        time.sleep(0.3)
    print("  encerrando o painel")
    httpd.shutdown()
    return 0
