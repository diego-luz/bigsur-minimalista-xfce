/* ===========================================================================
   d3bian-init-bigsur-minimalista-xfce - pecas comuns das paginas
   - faixa de estado do topo
   - Terminal: painel fixo no rodape que acompanha a tarefa do servidor, com
     etapas, progresso, log e um quadro claro quando termina
   Tudo fica dentro desta funcao: as paginas ja declaram o proprio `$`.
   =========================================================================== */
(() => {
"use strict";

const el = (tag, classe, texto) => {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined) e.textContent = texto;
  return e;
};
const doisDigitos = n => String(n).padStart(2, "0");
const relogio = segundos => {
  const s = Math.max(0, Math.floor(segundos));
  const h = s / 3600 | 0, m = (s / 60 | 0) % 60;
  return (h ? doisDigitos(h) + ":" : "") + doisDigitos(m) + ":" + doisDigitos(s % 60);
};
const duracao = segundos => segundos < 60 ? `${Math.max(1, segundos | 0)} s` : `${segundos / 60 | 0} min`;

// ---- faixa de estado do topo -----------------------------------------------

// o nome da verificacao nao diz o que fazer; a faixa precisa dizer
const O_QUE_FAZER = {
  "Permissao de administrador": "abra o painel pelo comando d3bian-init-bigsur-minimalista-xfce",
  "Acesso aos repositorios": "sem acesso aos repositórios do Debian",
  "Sistema": "este sistema não é Debian",
  "Ambiente grafico": "precisa do XFCE",
  "Sessao grafica": "abra dentro da sessão gráfica",
  "xfconf-query": "falta o xfconf",
  "Espaco em disco": "pouco espaço em disco",
};

function faixa(){
  const barra = document.querySelector(".estado");
  if (!barra) return;
  const por = (id, txt) => { const e = document.getElementById(id); if (e) e.textContent = txt; };
  const inicio = Date.now();
  setInterval(() => por("eTempo", relogio((Date.now() - inicio) / 1000)), 1000);

  fetch("/api/verificacoes").then(r => r.json()).then(d => {
    const achar = n => (d.verificacoes || []).find(c => c.nome === n) || {};
    por("eDistro", (achar("Sistema").detalhe || "desconhecido").replace(/GNU\/Linux /, ""));
    por("eDesktop", achar("Ambiente grafico").detalhe || "desconhecido");
    const imp = d.impedimentos || [];
    barra.classList.toggle("atencao", imp.length > 0);
    por("ePronto", imp.length ? "atenção" : "pronto");
    por("eSit", imp.length ? "[ " + imp.map(n => O_QUE_FAZER[n] || n).join("; ") + " ]" : "[ ok ]");
  }).catch(() => {
    barra.classList.add("atencao");
    por("ePronto", "desligado");
    por("eSit", "[ servidor fora do ar ]");
  });
}

// ---- terminal --------------------------------------------------------------

const Terminal = (() => {
  const MAX_VISIVEIS = 3000;     // linhas no DOM; o texto inteiro fica para copiar
  const p = {};                  // pecas do DOM
  let montado = false;
  let linhas = [], lidas = 0, falhas = 0, timer = null, relogioTimer = null;
  let rodando = false, repondo = false, seguir = true;
  let etapas = [], porPacote = false, pctApt = null, atual = "";
  let inicioLocal = 0, inicioServidor = null, desvio = 0;
  let opcoes = {}, ouvintes = [], resultado = null;
  const tituloOriginal = document.title;

  function montar(){
    if (montado) return;
    montado = true;
    p.raiz = el("section", "terminal");
    p.raiz.hidden = true;
    p.raiz.setAttribute("aria-label", "Terminal da tarefa");

    const topo = el("div", "t-topo");
    p.ponto = el("span", "t-estado");
    p.titulo = el("b", "t-titulo", "Tarefa");
    p.atual = el("span", "t-atual");
    p.pct = el("span", "t-pct");
    p.tempo = el("span", "t-tempo", "00:00");
    p.btMin = el("button", "t-bt", "minimizar");
    p.btFechar = el("button", "t-bt", "fechar");
    p.btMin.type = p.btFechar.type = "button";
    topo.append(p.ponto, p.titulo, p.atual, p.pct, p.tempo, p.btMin, p.btFechar);

    p.barra = el("div", "t-progresso");
    p.cheio = el("span");
    p.barra.appendChild(p.cheio);

    p.corpo = el("div", "t-corpo");
    p.lista = el("ol", "t-etapas");
    p.log = el("div", "t-log");
    p.log.setAttribute("role", "log");
    p.log.tabIndex = 0;
    p.corpo.append(p.lista, p.log);

    const rodape = el("div", "t-rodape");
    const rot = el("label");
    p.seguir = el("input");
    p.seguir.type = "checkbox"; p.seguir.checked = true;
    rot.append(p.seguir, document.createTextNode("seguir o fim"));
    p.btCopiar = el("button", "t-bt", "copiar log");
    p.btCopiar.type = "button";
    p.dica = el("span", "t-dica", "Deixe esta página aberta.");
    rodape.append(rot, p.btCopiar, p.dica);

    p.raiz.append(topo, p.barra, p.corpo, rodape);
    document.body.appendChild(p.raiz);

    // o espaco que o painel ocupa vira folga no fim da pagina e altura das
    // barras fixas, senao ele cobre o botao que a pessoa quer apertar
    new ResizeObserver(() => {
      const h = p.raiz.hidden ? 0 : p.raiz.offsetHeight;
      document.documentElement.style.setProperty("--term-h", h + "px");
    }).observe(p.raiz);

    p.btMin.addEventListener("click", e => { e.stopPropagation(); minimizar(!p.raiz.classList.contains("min")); });
    topo.addEventListener("click", () => { if (p.raiz.classList.contains("min")) minimizar(false); });
    p.btFechar.addEventListener("click", e => { e.stopPropagation(); fechar(); });
    p.btCopiar.addEventListener("click", copiar);
    p.seguir.addEventListener("change", () => { seguir = p.seguir.checked; if (seguir) aoFim(); });
    // rolar para cima desliga o "seguir"; voltar ao fim liga de novo
    p.log.addEventListener("scroll", () => {
      seguir = p.log.scrollHeight - p.log.scrollTop - p.log.clientHeight < 30;
      p.seguir.checked = seguir;
    });

    p.quadro = el("dialog", "t-quadro");
    document.body.appendChild(p.quadro);
    p.quadro.addEventListener("close", () => { document.title = tituloOriginal; });
  }

  // ---- estado visivel -------------------------------------------------------

  function minimizar(sim){
    p.raiz.classList.toggle("min", sim);
    p.btMin.textContent = sim ? "expandir" : "minimizar";
    if (!sim && seguir) aoFim();
  }

  function fechar(){
    if (rodando) return;
    p.raiz.hidden = true;
    document.documentElement.style.setProperty("--term-h", "0px");
  }

  function aoFim(){ p.log.scrollTop = p.log.scrollHeight; }

  function classe(linha){
    if (/^==> /.test(linha)) return "l-etapa";
    if (/^\s*concluido:/.test(linha)) return "l-ok";
    if (/\bERRO\b|^E: |^pmerror:|erro inesperado|nao consegui|não consegui/i.test(linha)) return "l-erro";
    if (/^W: |atencao:/i.test(linha)) return "l-alerta";
    return "";
  }

  function acrescentar(novas){
    const fragmento = document.createDocumentFragment();
    novas.forEach(linha => {
      if (!ler(linha)) return;
      linhas.push(linha);
      const s = el("span", classe(linha), linha + "\n");
      fragmento.appendChild(s);
    });
    p.log.appendChild(fragmento);
    while (p.log.childElementCount > MAX_VISIVEIS) p.log.firstElementChild.remove();
    if (seguir) aoFim();
  }

  // ---- leitura das linhas -----------------------------------------------------
  // devolve false para as linhas de maquina, que viram progresso e somem do log

  function ler(linha){
    let m;
    // apt com APT::Status-Fd: baixar vale 30% da barra, instalar os outros 70%
    if ((m = linha.match(/^pmstatus:(.+?):([\d.]+):(.*)$/))){
      const pkg = m[1].split(":")[0];
      if (pkg !== "dpkg-exec") marcarPacote(pkg);
      pctApt = 30 + parseFloat(m[2]) * 0.7;
      atual = m[3];
      return false;
    }
    if ((m = linha.match(/^dlstatus:\d+:([\d.]+):(.*)$/))){
      pctApt = parseFloat(m[1]) * 0.3;
      atual = m[2];
      return false;
    }
    if ((m = linha.match(/^==> (\S+) (.*)$/))){ iniciarEtapa(m[1], m[2]); return true; }
    if (/^\s*concluido:/.test(linha)){ fecharEtapa("feito"); return true; }
    if (/^\s*ERRO/.test(linha)){ fecharEtapa("erro"); return true; }
    if ((m = linha.match(/^\s*ja aplicado: (\S+)/))){ mudar(m[1], "feito"); return true; }
    if ((m = linha.match(/^\s*pulando (\S+)/))){ mudar(m[1], "pulado"); return true; }
    if ((m = linha.match(/^habilitando a fonte de (.*?):/))) atual = "Habilitando a fonte de " + m[1];
    return true;
  }

  const achar = id => etapas.find(e => e.id === id);
  const agora = () => Date.now() / 1000;

  function mudar(id, estado){
    const e = achar(id);
    if (!e) return;
    if (estado === "rodando" && e.estado !== "rodando") e.inicio = repondo ? null : agora();
    if (estado !== "rodando" && e.estado === "rodando" && e.inicio) e.fim = agora();
    e.estado = estado;
  }

  function iniciarEtapa(id, nome){
    if (!achar(id)) etapas.push({id, nome, estado: "espera"});
    etapas.filter(e => e.estado === "rodando").forEach(e => mudar(e.id, "feito"));
    mudar(id, "rodando");
    atual = nome;
  }

  function fecharEtapa(estado){
    etapas.filter(e => e.estado === "rodando").forEach(e => mudar(e.id, estado));
  }

  function marcarPacote(pkg){
    porPacote = true;
    const e = achar(pkg);
    if (!e || e.estado === "rodando") return;
    etapas.filter(x => x.estado === "rodando").forEach(x => mudar(x.id, "feito"));
    mudar(pkg, "rodando");
  }

  function porcentagem(){
    if (pctApt !== null) return Math.min(100, pctApt);
    if (!etapas.length) return null;
    const prontas = etapas.filter(e => ["feito", "pulado", "erro"].includes(e.estado)).length;
    return prontas / etapas.length * 100;
  }

  function desenhar(){
    const pct = porcentagem();
    p.barra.classList.toggle("indefinido", pct === null && rodando);
    p.cheio.style.width = pct === null ? "" : pct.toFixed(1) + "%";
    p.pct.textContent = pct === null ? "" : Math.floor(pct) + "%";

    const rodandoAgora = etapas.find(e => e.estado === "rodando");
    const indice = rodandoAgora ? etapas.indexOf(rodandoAgora) + 1 : 0;
    let texto = atual;
    if (rodandoAgora && etapas.length) texto = `Etapa ${indice} de ${etapas.length} · ${rodandoAgora.nome}`
                                             + (porPacote && atual ? ` · ${atual}` : "");
    p.atual.textContent = texto;
    p.atual.title = texto;
    if (rodando) document.title = (pct === null ? "" : Math.floor(pct) + "% · ") + (opcoes.titulo || "Tarefa");

    p.corpo.classList.toggle("sem-etapas", etapas.length === 0);
    p.lista.textContent = "";
    const MARCAS = {espera: "·", rodando: "▸", feito: "✓", erro: "✗", pulado: "–"};
    etapas.forEach(e => {
      const li = el("li", e.estado);
      li.append(el("span", "mk", MARCAS[e.estado]), el("span", "nm", e.nome));
      li.title = e.nome;
      if (e.inicio){
        const s = (e.fim || agora()) - e.inicio;
        if (e.estado === "rodando" || s >= 5) li.appendChild(el("span", "dur", duracao(s)));
      }
      p.lista.appendChild(li);
    });
    const vivo = p.lista.querySelector("li.rodando, li.erro");
    if (vivo) p.lista.scrollTop = vivo.offsetTop - p.lista.clientHeight / 2;
  }

  function atualizarTempo(){
    const s = inicioServidor !== null ? agora() - desvio - inicioServidor : agora() - inicioLocal;
    p.tempo.textContent = relogio(s);
    return s;
  }

  // ---- ciclo com o servidor ---------------------------------------------------

  async function passo(){
    let r = null;
    try { r = await fetch("/api/progresso?desde=" + lidas).then(x => x.json()); }
    catch (e) { r = null; }
    if (!r){
      if (++falhas >= 8) await terminar(null);
      return;
    }
    falhas = 0;
    if (typeof r.inicio === "number" && typeof r.agora === "number"){
      inicioServidor = r.inicio;
      desvio = agora() - r.agora;
    }
    if (r.linhas && r.linhas.length){
      lidas = r.total;
      acrescentar(r.linhas);
    }
    repondo = false;
    desenhar();
    if (!r.rodando && r.codigo !== null) await terminar(r.codigo);
  }

  async function ciclo(){
    await passo();
    if (rodando) timer = setTimeout(ciclo, 700);
  }

  const segurar = e => { e.preventDefault(); e.returnValue = ""; };

  function abrir(o){
    montar();
    clearTimeout(timer); clearInterval(relogioTimer);
    opcoes = o || {};
    linhas = []; lidas = 0; falhas = 0; seguir = true; p.seguir.checked = true;
    etapas = (opcoes.etapas || []).map(e => ({id: String(e.id), nome: e.nome, estado: "espera"}));
    porPacote = false; pctApt = null; atual = opcoes.atual || ""; resultado = null;
    inicioLocal = agora(); inicioServidor = null; repondo = !!opcoes.repondo;
    p.log.textContent = "";
    p.titulo.textContent = opcoes.titulo || "Tarefa";
    p.dica.textContent = opcoes.dica || "Deixe esta página aberta.";
    p.raiz.classList.remove("ok", "erro", "min");
    p.raiz.classList.add("rodando");
    p.btMin.textContent = "minimizar";
    p.btFechar.hidden = true;
    p.raiz.hidden = false;
    rodando = true;
    ouvintes.forEach(fn => fn(true));
    window.addEventListener("beforeunload", segurar);
    relogioTimer = setInterval(() => { atualizarTempo(); if (etapas.some(e => e.estado === "rodando")) desenhar(); }, 1000);
    desenhar();
    ciclo();
  }

  async function terminar(codigo){
    if (!rodando) return;
    rodando = false;
    clearTimeout(timer); clearInterval(relogioTimer);
    window.removeEventListener("beforeunload", segurar);
    const s = atualizarTempo();
    if (codigo === 0){
      etapas.forEach(e => {
        if (e.estado === "rodando" || (porPacote && e.estado === "espera")) mudar(e.id, "feito");
      });
      if (pctApt !== null) pctApt = 100;
      atual = "Terminou sem erros";
    } else {
      fecharEtapa("erro");
      atual = codigo === null ? "Sem contato com o servidor" : `Terminou com erro (código ${codigo})`;
    }
    p.raiz.classList.remove("rodando");
    p.raiz.classList.add(codigo === 0 ? "ok" : "erro");
    p.btFechar.hidden = false;
    p.dica.textContent = codigo === 0 ? "" : "As linhas em vermelho mostram onde parou.";
    desenhar();
    ouvintes.forEach(fn => fn(false));

    let msg = null;
    try { msg = opcoes.aoTerminar ? await opcoes.aoTerminar(codigo) : null; }
    catch (e) { msg = null; }
    resultado = {codigo, ...padrao(codigo), ...(msg || {})};
    if (codigo !== 0){
      const erro = p.log.querySelector(".l-erro");
      if (erro){ seguir = false; p.seguir.checked = false; p.log.scrollTop = erro.offsetTop - 40; }
    }
    quadro(resultado, s);
  }

  function padrao(codigo){
    if (codigo === 0) return {bom: true, titulo: "Concluído", texto: `${opcoes.titulo || "A tarefa"} terminou sem erros.`};
    if (codigo === null) return {bom: false, titulo: "Sem contato com o servidor",
      texto: "O painel local parou de responder. Veja o terminal onde ele foi aberto."};
    return {bom: false, titulo: "Terminou com erro", texto: `Código ${codigo}. O log mostra onde parou.`};
  }

  // ---- quadro de conclusao ------------------------------------------------------

  function quadro(r, segundos){
    const q = p.quadro;
    q.className = "t-quadro " + (r.bom ? "ok" : "erro");
    q.textContent = "";
    const ic = el("div", "ic", r.bom ? "✓" : "✗");
    ic.setAttribute("aria-hidden", "true");
    const tt = el("p", "tt", r.titulo);
    tt.id = "tQuadroTitulo";
    q.setAttribute("aria-labelledby", "tQuadroTitulo");
    q.append(ic, tt);
    if (r.texto) q.appendChild(el("p", "tx", r.texto));
    if (segundos) q.appendChild(el("p", "dur", "Tempo total: " + relogio(segundos)));
    if (r.itens && r.itens.length){
      const ul = el("ul");
      r.itens.forEach(x => ul.appendChild(el("li", "", x)));
      q.appendChild(ul);
    }
    const acoes = el("div", "acoes");
    const verLog = el("button", "bt sec", "Ver o log");
    const ok = el("button", "bt pri", r.bom ? "Fechar" : "Entendi");
    verLog.type = ok.type = "button";
    verLog.addEventListener("click", () => { q.close(); minimizar(false); p.log.focus(); });
    ok.addEventListener("click", () => { q.close(); if (r.bom) minimizar(true); });
    acoes.append(verLog, ok);
    q.appendChild(acoes);

    // quem estiver em outra aba ve o resultado no titulo
    document.title = (r.bom ? "✓ " : "✗ ") + r.titulo + " · d3bian-init-bigsur-minimalista-xfce";
    if (q.open) q.close();
    q.showModal();
    ok.focus();
  }

  async function copiar(){
    const texto = linhas.join("\n");
    let deu = false;
    try { await navigator.clipboard.writeText(texto); deu = true; }
    catch (e) {
      const area = el("textarea");
      area.value = texto;
      area.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(area);
      area.select();
      try { deu = document.execCommand("copy"); } catch (e2) { deu = false; }
      area.remove();
    }
    p.btCopiar.textContent = deu ? "copiado" : "não consegui copiar";
    setTimeout(() => { p.btCopiar.textContent = "copiar log"; }, 1800);
  }

  // ---- o que as paginas usam ------------------------------------------------------

  return {
    // abre o painel para a tarefa que o servidor acabou de comecar.
    // o: {titulo, etapas: [{id, nome}], dica, aoTerminar(codigo) -> {bom, titulo, texto, itens}}
    acompanhar: abrir,

    // na carga da pagina: se o servidor ja roda algo, reabre o painel com o log
    // desde o comeco. o: {titulo(rotulo), etapas(rotulo), aoTerminar(codigo)}
    async retomar(o = {}){
      let r;
      try { r = await fetch("/api/progresso?desde=0").then(x => x.json()); }
      catch (e) { return false; }
      if (!r || !r.rodando) return false;
      abrir({
        titulo: (o.titulo && o.titulo(r.rotulo)) || r.rotulo || "Tarefa em andamento",
        etapas: (o.etapas && o.etapas(r.rotulo)) || [],
        aoTerminar: o.aoTerminar,
        repondo: true,
      });
      return true;
    },

    // fn(ocupado) e chamada quando uma tarefa comeca e quando termina
    aoMudar(fn){ ouvintes.push(fn); if (rodando) fn(true); },
    ocupado: () => rodando,

    // quadro avulso, para erro antes de a tarefa comecar
    avisar(bom, titulo, texto, itens){ montar(); quadro({bom, titulo, texto, itens}, 0); },
  };
})();

window.Terminal = Terminal;
// este arquivo carrega antes do corpo da pagina; a faixa espera ele existir
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", faixa);
else faixa();
})();
