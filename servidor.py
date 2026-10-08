"""Painel web local.

Escuta so em 127.0.0.1. Ele executa coisas na maquina, entao nao deve ficar
acessivel pela rede. Quem quiser usar de outro computador que faca tunel SSH.
"""

from __future__ import annotations

import hmac
import html
import json
import os
import secrets
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import (caminhos, capturas, config, estado, papeis, programas,
               receitas, sistema)
from .tarefa import Tarefa

PORTA_PADRAO = 8974

TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".svg": "image/svg+xml",
    ".ico": "image/x-icon", ".woff2": "font/woff2",
}

NOME = "d3bian-init-bigsur-minimalista-xfce"

tarefa = Tarefa()
parar = threading.Event()

# Acesso: so a pagina aberta pelo link do terminal fala com a API. O link traz
# um codigo de uso unico (ENTRADA) que vira um cookie secreto (CHAVE); sem ele,
# um site qualquer aberto no navegador (ou outro usuario da maquina) nao
# consegue mandar o painel instalar, desfazer ou apagar nada.
CHAVE = secrets.token_urlsafe(32)
_entrada = {"codigo": secrets.token_urlsafe(32)}
_trava_entrada = threading.Lock()


def link_de_entrada(porta: int) -> str:
    return f"http://127.0.0.1:{porta}/entrar?k={_entrada['codigo']}"


def _arquivo_de_entrada(porta: int) -> Path:
    """O link vai num arquivo so da pessoa, nao na linha de comando: a lista de
    processos (/proc/*/cmdline) e visivel para as outras contas da maquina."""
    base = os.environ.get("XDG_RUNTIME_DIR") or str(caminhos.ESTADO_DIR)
    alvo = Path(base) / f"{NOME}-entrar.html"
    link = html.escape(link_de_entrada(porta))
    caminhos.escrever(alvo, f"<!doctype html><meta charset=utf-8>"
                            f"<meta http-equiv=refresh content='0;url={link}'>"
                            f"<a href='{link}'>abrir o painel</a>\n", 0o600)
    return alvo


def _uid_da_conexao(porta_cliente: int, porta_servidor: int) -> int | None:
    """Dono da conexao, pela tabela do kernel; None se nao der para saber."""
    try:
        linhas = Path("/proc/net/tcp").read_text().splitlines()[1:]
    except OSError:
        return None
    for linha in linhas:
        campos = linha.split()
        try:
            local, remoto, uid = campos[1], campos[2], int(campos[7])
        except (IndexError, ValueError):
            continue
        if (int(local.split(":")[1], 16) == porta_cliente
                and int(remoto.split(":")[1], 16) == porta_servidor):
            return uid
    return -1  # conexao que nao aparece: recusa


def _nome_cookie(porta: int) -> str:
    # cookies nao separam portas: cada painel usa o seu nome
    return f"painel_{porta}"


ACESSO_HTML = ("<!doctype html><meta charset=utf-8><title>" + html.escape(NOME) + "</title>"
               "<body style='font-family:sans-serif;max-width:36em;margin:4em auto;line-height:1.5'>"
               "<h1>Abra pelo link do terminal</h1><p>Por segurança, este painel só aceita a janela "
               "aberta pelo link que aparece no terminal onde ele está rodando (o link vale uma vez; "
               "depois de usado, o terminal mostra outro).</p>").encode()


class Painel(BaseHTTPRequestHandler):
    server_version = NOME

    def log_message(self, *_a) -> None:
        pass

    # ---- acesso ----------------------------------------------------------
    def _porta(self) -> int:
        return self.server.server_address[1]

    def _host_ok(self) -> bool:
        # contra DNS rebinding: um site que aponta o proprio nome para
        # 127.0.0.1 chega aqui com o Host dele
        porta = self._porta()
        return self.headers.get("Host", "") in (f"127.0.0.1:{porta}", f"localhost:{porta}")

    def _sessao_ok(self) -> bool:
        # le o cabecalho a mao: um cookie malformado de outro programa em
        # 127.0.0.1 (cookies nao separam portas) nao pode travar o painel
        nome = _nome_cookie(self._porta()) + "="
        for parte in self.headers.get("Cookie", "").split(";"):
            parte = parte.strip()
            if parte.startswith(nome) and hmac.compare_digest(parte[len(nome):], CHAVE):
                return True
        return False

    def _mesmo_usuario(self) -> bool:
        """So a conta que abriu o painel fala com ele: outra conta da maquina
        tambem alcanca 127.0.0.1, entao a conexao e conferida pelo dono."""
        return _uid_da_conexao(self.client_address[1], self._porta()) in (os.getuid(), None)

    def _post_ok(self) -> bool:
        porta = self._porta()
        origem = self.headers.get("Origin")
        if origem is not None and origem not in (f"http://127.0.0.1:{porta}", f"http://localhost:{porta}"):
            return False
        # JSON obriga o navegador a perguntar antes (preflight), que nao respondemos
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return False
        return self._sessao_ok()

    def _negado(self) -> None:
        self.json({"motivo": "acesso", "detalhe": "abra o painel pelo link mostrado no terminal"}, 403)

    def _entrar(self) -> None:
        recebido = self.path.split("k=", 1)[1].split("&")[0] if "k=" in self.path else ""
        porta = self._porta()
        with _trava_entrada:
            valido = bool(recebido) and hmac.compare_digest(recebido, _entrada["codigo"])
            if valido:
                # uso unico: o link pode ter ficado no historico ou na lista de
                # processos; o terminal mostra um novo para outra janela
                _entrada["codigo"] = secrets.token_urlsafe(32)
                print(f"  uma janela entrou no painel ({time.strftime('%H:%M:%S')})")
                print(f"  para abrir em outra janela: {link_de_entrada(porta)}")
        if not valido:
            self._envia(403, ACESSO_HTML, "text/html; charset=utf-8")
            return
        # a janela chega aqui pelo arquivo local que o xdg-open abriu, e o
        # navegador trata essa navegacao como vinda de outro site: o cookie Strict
        # nao iria num redirecionamento para "/" e a pagina pediria o link de
        # novo. Daqui a ida para "/" ja sai do proprio painel, e o cookie vai junto
        corpo = (b"<!doctype html><meta charset=utf-8>"
                 b"<meta http-equiv=refresh content='0;url=/'>"
                 b"<script>location.replace('/')</script>"
                 b"<a href='/'>abrir o painel</a>\n")
        self.send_response(200)
        self.send_header("Set-Cookie", f"{_nome_cookie(porta)}={CHAVE}; HttpOnly; SameSite=Strict; Path=/")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

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
        if not self._mesmo_usuario():
            self._envia(403, b"outra conta", "text/plain; charset=utf-8")
            return
        if not self._host_ok():
            self._envia(403, b"host nao permitido", "text/plain; charset=utf-8")
            return
        rota = self.path.split("?")[0]
        if rota == "/entrar":
            self._entrar()
            return
        if rota == "/":
            rota = "/index.html"
        if rota.startswith("/api/") and not self._sessao_ok():
            self._negado()
            return
        # previas e papeis sao fotos desta maquina (e a miniatura roda o
        # ImageMagick): so com a sessao. Livres ficam css, js e os logos do pacote
        if rota.startswith(("/capturas/", "/papeis/")) and not self._sessao_ok():
            self._envia(403, b"abra o painel pelo link do terminal", "text/plain; charset=utf-8")
            return
        if rota.endswith(".html") and not self._sessao_ok():
            # a pagina sem a sessao nao serviria para nada: explica o que fazer
            self._envia(403, ACESSO_HTML, "text/html; charset=utf-8")
            return

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

        if rota == "/api/desfazer/previa":
            from . import desfazer
            self.json(desfazer.previa_remocao())
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
            # por nome: antes do download a galeria mostra as miniaturas do pacote
            atual = papeis.nome_escolhido(config.ler())
            # o esquema da pagina precisa saber o que "do tema" escolheria
            do_tema = {t: papeis.nome_escolhido({"tema": t, "papel_de_parede": "do-tema"}) or ""
                       for t in ("escuro", "claro")}
            self.json({"papeis": papeis.disponiveis(), "doTema": do_tema,
                       "baixados": papeis.baixados(), "emUso": atual or ""})
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
        # "/index.html/" resolve para a pagina: a regra vale pelo arquivo, nao pelo texto
        if alvo.suffix == ".html" and not self._sessao_ok():
            self._envia(403, ACESSO_HTML, "text/html; charset=utf-8")
            return
        if not alvo.is_relative_to(caminhos.WEB.resolve()):
            self._envia(404, b"nao encontrado", "text/plain; charset=utf-8")
            return
        self.arquivo(alvo)

    # ---- POST ------------------------------------------------------------
    def do_POST(self) -> None:
        # toda rota POST passa por aqui: acao so com a sessao, em JSON e da
        # propria pagina
        if not (self._mesmo_usuario() and self._host_ok() and self._post_ok()):
            self._negado()
            return
        rota = self.path.split("?")[0]
        corpo = self.corpo()

        if rota == "/api/sair":
            # sair no meio do apt deixaria o dpkg pela metade
            if tarefa.ocupada():
                self.json({"tchau": False, "motivo": "ocupado", "detalhe": tarefa.rotulo}, 409)
                return
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
        if rota == "/api/desfazer":
            from . import desfazer
            apagar = bool(corpo.get("apagar"))
            iniciado = tarefa.funcao("Desfazendo" + (" e apagando" if apagar else ""),
                                     lambda diz: desfazer.executar(diz, apagar))
            self.json({"iniciado": iniciado, "motivo": "" if iniciado else "ocupado",
                       "etapas": [{"id": i, "nome": n} for i, n in desfazer.etapas(apagar)]},
                      200 if iniciado else 409)
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

        if not caminhos.livre():
            self.json({"iniciado": False, "motivo": "ocupado",
                       "detalhe": "a linha de comando esta rodando"}, 409)
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
                "/etc/lightdm/lightdm.conf.d/91-d3bian-minimalista.conf").read_text()
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
        if not caminhos.livre():
            self.json({"iniciado": False, "motivo": "ocupado",
                       "detalhe": "a linha de comando esta rodando"}, 409)
            return
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

        if not caminhos.livre():
            self.json({"iniciado": False, "motivo": "ocupado",
                       "detalhe": "a linha de comando esta rodando"}, 409)
            return
        if remover:
            extras = programas.arrastaria(escolhidos)
            if extras and not corpo.get("confirmar"):
                self.json({"iniciado": False, "motivo": "arrasta_outros",
                           "extras": extras})
                return
            rotulo = "Removendo: " + ", ".join(escolhidos)
            iniciado = tarefa.funcao(
                rotulo, lambda diz: programas.remover(escolhidos, diz))
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

    endereco = link_de_entrada(porta)
    print(f"\n  {NOME} aberto em {endereco}")
    print("  (o link vale uma vez; feche pelo botao na pagina, ou com Ctrl+C aqui)\n")
    if abrir:
        try:
            subprocess.Popen(["xdg-open", _arquivo_de_entrada(porta).as_uri()],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            print("  abra o endereco acima no seu navegador")

    def encerrar(*_a) -> None:
        # no meio de uma tarefa, o 1o Ctrl+C so avisa: o apt pela metade
        # deixaria o dpkg quebrado; o 2o encerra assim mesmo
        if tarefa.ocupada() and not encerrar.avisou:
            encerrar.avisou = True
            print("\n  ainda instalando: espere terminar, ou Ctrl+C de novo para sair assim mesmo")
            return
        parar.set()
    encerrar.avisou = False
    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)
    while not parar.is_set():
        time.sleep(0.3)
    print("  encerrando o painel")
    httpd.shutdown()
    return 0
