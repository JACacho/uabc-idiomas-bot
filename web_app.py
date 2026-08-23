PAGINA = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UABCBot Idiomas — Facultad de Idiomas de la UABC en Mexicali</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { background: #eef1f4; }
  #toast { display: none; position: fixed; top: 12px; left: 50%; transform: translateX(-50%); color: #fff; padding: 13px 22px; border-radius: 14px; font-size: 14.5px; z-index: 99; box-shadow: 0 4px 16px rgba(0,0,0,.35); max-width: 92%; text-align: center; }
  .wrap { max-width: 1400px; margin: 0 auto; height: 100vh; display: flex; flex-direction: row; }
  #side { width: 280px; background: #004d38; color: #fff; padding: 14px 10px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
  #side b { font-size: 14px; }
  #side button { background: rgba(255,255,255,.12); color: #fff; border: none; border-radius: 10px; padding: 9px 10px; text-align: left; cursor: pointer; font-size: 12.5px; }
  #side button:hover { background: rgba(255,255,255,.25); }
  main { flex: 1; display: flex; flex-direction: column; height: 100vh; }
  header { background: linear-gradient(135deg, #00684a, #00855f); color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 12px; border-radius: 0 0 18px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.15); flex-wrap: wrap; }
  header img { width: 54px; height: 54px; background: #fff; border-radius: 12px; padding: 3px; }
  header h1 { font-size: 17px; } header p { font-size: 12px; opacity: .85; }
  .langs { display: flex; gap: 5px; margin-left: 14px; flex-wrap: wrap; }
  .langs button { font-size: 11px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: transparent; color: #fff; cursor: pointer; }
  .langs button.on { background: #f7941d; border-color: #f7941d; font-weight: 700; }
  .utils { display: flex; gap: 5px; margin-left: auto; }
  .utils button { font-size: 14px; padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: rgba(255,255,255,.15); color: #fff; cursor: pointer; }
  .utils button:hover { background: rgba(255,255,255,.3); }
  .hbtn { background: rgba(255,255,255,.15); border: none; border-radius: 999px; width: 36px; height: 36px; cursor: pointer; font-size: 16px; }
  #nuevo { margin-left: auto; }
  #chat { flex: 1; overflow-y: auto; padding: 16px 12px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 82%; display: flex; flex-direction: column; gap: 4px; }
  .msg.user { align-self: flex-end; align-items: flex-end; }
  .msg.bot { align-self: flex-start; align-items: flex-start; }
  .bub { padding: 10px 14px; border-radius: 16px; font-size: calc(14.5px * var(--fs, 1)); line-height: 1.45; box-shadow: 0 1px 2px rgba(0,0,0,.12); white-space: pre-wrap; }
  .user .bub { background: #d9f6c8; border-bottom-right-radius: 4px; }
  .bot .bub { background: #fff; border-bottom-left-radius: 4px; }
  .msg audio { width: 260px; max-width: 100%; }
  .think .bub { background: #fff; color: #666; font-style: italic; }
  .dots::after { content: ''; animation: pts 1.2s steps(4) infinite; }
  @keyframes pts { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75% { content: '...'; } }
  .opts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .opts button { font-size: calc(12.5px * var(--fs, 1)); padding: 7px 11px; border-radius: 999px; border: 1px solid #00855f; background: #f2fbf6; color: #00684a; cursor: pointer; }
  .opts button:hover { background: #00855f; color: #fff; }
  .nota { display: block; margin-top: 9px; font-size: calc(12px * var(--fs, 1)); color: #888; }
  .bar { display: flex; gap: 8px; padding: 10px 12px 14px; align-items: center; }
  #mic { width: 46px; height: 46px; border-radius: 50%; border: none; background: #00684a; color: #fff; font-size: 19px; cursor: pointer; flex-shrink: 0; }
  #mic.rec { background: #d32f2f; animation: pulso 1s infinite; }
  @keyframes pulso { 50% { transform: scale(1.12); } }
  #inp { flex: 1; border: 1px solid #cfd8dc; border-radius: 999px; padding: 12px 18px; font-size: calc(15px * var(--fs, 1)); outline: none; }
  #inp:focus { border-color: #00855f; }
  #send { width: 46px; height: 46px; border-radius: 50%; border: none; background: #f7941d; color: #fff; font-size: 18px; cursor: pointer; flex-shrink: 0; }
  #fb { width: 46px; height: 46px; border-radius: 50%; border: none; background: #d32f2f; color: #fff; font-size: 17px; cursor: pointer; flex-shrink: 0; }
  #gear { position: fixed; right: 10px; top: 74px; background: rgba(0,0,0,.25); border: none; color: #fff; border-radius: 50%; width: 30px; height: 30px; cursor: pointer; z-index: 5; }
  #convs { display: none; }
  .drawer { display: none; background: #fff; margin: 0 12px 8px; border-radius: 14px; padding: 12px; box-shadow: 0 2px 10px rgba(0,0,0,.15); font-size: 13px; max-height: 60vh; overflow-y: auto; }
  .drawer input, .drawer select, .drawer textarea { margin: 4px 0; padding: 8px; border-radius: 8px; border: 1px solid #cfd8dc; width: 100%; }
  .drawer button { margin-top: 6px; padding: 8px 12px; border-radius: 10px; border: none; background: #00684a; color: #fff; cursor: pointer; }
  .drawer .item { display: block; width: 100%; background: #f2f4f7; color: #222; margin: 4px 0; text-align: left; }
  .xbtn { background: #d32f2f !important; float: right; }
  #drop { border: 2px dashed #00855f; border-radius: 12px; padding: 14px; text-align: center; color: #00684a; background: #f2fbf6; margin: 6px 0; cursor: pointer; }
  #dlist { white-space: pre-wrap; background: #f7f9fa; border-radius: 8px; padding: 8px; margin-top: 6px; font-size: 12px; }
  .etiq { display: block; margin: 8px 0 2px; font-weight: 700; color: #00684a; }
  .ayuda { font-size: 11.5px; color: #667; margin-bottom: 4px; }
  @media (max-width: 900px) { #side { display: none; } #convs { display: block; } }
  @media (min-width: 900px) {
    .bub { font-size: calc(16.5px * var(--fs, 1)); }
    header h1 { font-size: 21px; }
    header p { font-size: 13px; }
    #inp { font-size: calc(17px * var(--fs, 1)); padding: 14px 22px; }
    .msg { max-width: 70%; }
  }
</style>
</head>
<body>
<div id="toast"></div>
<div class="wrap">
  <aside id="side">
    <b>🗂️ Conversaciones</b>
    <button id="nueva">➕ Nueva conversación</button>
    <div id="lista"></div>
  </aside>
  <main>
    <header>
      <img src="/logo.png" alt="logo">
      <div><h1>UABCBot Idiomas</h1><p>Facultad de Idiomas de la UABC en Mexicali</p></div>
      <div class="langs">
        <button id="Lauto" class="on">AUTO</button><button id="Les">ES</button><button id="Len">EN</button><button id="Lfr">FR</button>
      </div>
      <div class="utils">
        <button id="fmenos" title="Reducir letra">A−</button>
        <button id="fmas" title="Aumentar letra">A+</button>
        <button id="full" title="Pantalla completa">⛶</button>
      </div>
      <button id="convs" class="hbtn" title="Conversaciones">🗂️</button>
      <button id="user" class="hbtn" title="Tu cuenta">👤</button>
      <button id="nuevo" class="hbtn" title="Nueva conversación">🧹</button>
    </header>
    <button id="gear" title="Personal autorizado">⚙️</button>
    <div id="cdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button><b>️ Conversaciones</b><div id="lista2"></div></div>
    <div id="udrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'"> Cerrar</button>
      <b> Tu cuenta</b>
      <div id="who"></div>
      <input id="uusr" placeholder="Usuario o correo">
      <input id="ukey" type="password" placeholder="Clave">
      <button id="ureg">✨ Registrarme</button>
      <button id="ulin">🔑 Entrar</button>
      <button id="uguest">👋 Seguir como invitado</button>
      <button id="uout">🚪 Cerrar sesión</button>
    </div>
    <div id="chat"></div>
    <div id="fbdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>🚩 Reportar respuesta no resuelta</b>
      <span class="etiq">Área responsable</span>
      <select id="fbarea">
        <option>Admisión</option><option>CEC</option><option>Escolar/Escolaridad</option><option>Egresados/Bolsa de trabajo</option><option>Eventos</option><option>Otro</option>
      </select>
      <span class="etiq">Cuéntanos qué faltó</span>
      <textarea id="fbcom" rows="3" placeholder="Ej. No me dijo la fecha exacta del examen de admisión…"></textarea>
      <button id="fbsend">📨 Enviar al responsable</button>
    </div>
    <div id="drawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>🛠️ Panel de personal</b>
      <input id="clave" type="password" placeholder="Clave de acceso (Enter para entrar)">
      <button id="unlock">🔓 Entrar</button>
      <button id="salirp">🚪 Salir del panel</button>
      <div id="zona" style="display:none">
        <span class="etiq">1️⃣ Categoría del aviso</span>
        <select id="fcat">
          <option>Avisos</option><option>Eventos</option><option>Suspensiones</option><option>Horarios</option><option>Exámenes</option><option>Convocatorias</option><option>TSU</option><option>PlanDeEstudios</option>
        </select>
        <span class="etiq">2️⃣ Vigente hasta (opcional)</span>
        <input id="fvig" type="date">
        <span class="etiq">3️⃣ Elige o arrastra el archivo (TXT, PDF o imagen)</span>
        <div id="drop">📥 Arrastra aquí tu documento o póster<br><small>o toca para elegirlo</small></div>
        <input id="ffile" type="file" style="display:none">
        <span class="etiq"> Texto del póster (plan B recomendado para imágenes)</span>
        <div class="ayuda">Si subes una IMAGEN y el motor de visión está saturado, copia y pega aquí lo que dice el póster (evento, fecha, hora, lugar) y se publicará al instante sin esperar.</div>
        <textarea id="ftexto" rows="4" placeholder="Ejemplo: Plática para Potenciales a Egresar. Martes 18 de agosto, 12:00 y 16:00 hrs, Sala de Usos Múltiples. Informes: Mtra. Dulce Rodríguez, egresados__idiomas__mxl@uabc.edu.mx"></textarea>
        <button id="fsubir"> Subir y publicar</button>
        <button id="nota">🎤 Grabar nota de voz</button>
        <button id="ldocs">🔄 Ver documentos</button>
        <button id="lfb">📨 Ver feedbacks</button>
        <button id="rep">📊 Reporte de uso</button>
        <div id="dlist"></div>
        <span class="etiq">️ Borrar un documento</span>
        <input id="fdel" placeholder="Nombre del documento a borrar (Enter borra)">
        <button id="bdel">🗑️ Borrar</button>
        <div id="fest"></div>
      </div>
    </div>
    <div class="bar">
      <button id="mic">🎤</button>
      <input id="inp" placeholder="Escribe o dime tu pregunta…">
      <button id="send"></button>
      <button id="fb" title="¿No te resolvió? Repórtalo">🚩</button>
    </div>
  </main>
</div>
<script>
let hist = [], state = {pending:false, active:false}, langPref = "auto", rec = null, rec2 = null, chunks = [], currentId = uid(), droppedFile = null, thinkTimer = null, thinkSec = 0, toastTimer = null, lastPregunta = "", lastRespuesta = "", fontScale = 1;
let currentUser = localStorage.getItem('uabc_user') || "";
const chat = document.getElementById('chat'), inp = document.getElementById('inp');
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function uid(){ return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2,7); }
function avisar(msg, tipo){
  const t = document.getElementById('toast');
  t.innerText = msg;
  t.style.background = tipo === 'error' ? '#d32f2f' : (tipo === 'ok' ? '#00684a' : '#f7941d');
  t.style.display = 'block';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = 'none'; }, 7000);
}
function bubble(role, text, audio){
  const d = document.createElement('div'); d.className = 'msg ' + role;
  let h = '<div class="bub">' + esc(text) + '</div>';
  if (audio) h += '<audio controls src="' + audio + '"></audio>';
  d.innerHTML = h; chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  return d;
}

// TEXTOS MULTILINGÜES
const TEXTOS = {
  es: {
    bienvenida: "👋 ¡Hola! Soy <b>UABCBot Idiomas</b>, el asistente de la Facultad de Idiomas de la UABC en Mexicali. Toca una opción o escribe/dime tu pregunta en español, inglés o francés.",
    nota: "Personal docente: escribe o di \"administración\". Si una respuesta no te resuelve, toca 🚩.",
    sugerencias: [
      {q: "¿Cuántos créditos necesito para titularme en Traducción?", t: "💳 Créditos para titularme"},
      {q: "¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?", t: "📅 Horarios del CEC"},
      {q: "¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?", t: "🎓 Requisitos de admisión"},
      {q: "¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?", t: "🏛️ Carreras y TSU"}
    ]
  },
  en: {
    bienvenida: " Hi! I'm <b>UABCBot Idiomas</b>, the assistant of the Faculty of Languages of UABC in Mexicali. Tap an option or type/tell me your question in Spanish, English or French.",
    nota: "Teaching staff: type or say \"administración\". If an answer doesn't solve your question, tap 🚩.",
    sugerencias: [
      {q: "How many credits do I need to graduate from Translation?", t: "💳 Credits to graduate"},
      {q: "What are the schedules of the Language Teaching Center (CEC)?", t: "📅 CEC schedules"},
      {q: "What are the admission requirements for the Faculty of Languages?", t: "🎓 Admission requirements"},
      {q: "What degrees and technical programs does the Faculty of Languages offer?", t: "🏛️ Degrees and TSU"}
    ]
  },
  fr: {
    bienvenida: "👋 Bonjour ! Je suis <b>UABCBot Idiomas</b>, l'assistant de la Faculté de Langues de l'UABC à Mexicali. Touchez une option ou écrivez/dites-moi votre question en espagnol, anglais ou français.",
    nota: "Personnel enseignant : écrivez ou dites \"administración\". Si une réponse ne vous aide pas, touchez 🚩.",
    sugerencias: [
      {q: "Combien de crédits faut-il pour obtenir son diplôme en Traduction ?", t: "💳 Crédits pour diplômer"},
      {q: "Quels sont les horaires du Centre d'Enseignement des Langues (CEC) ?", t: "📅 Horaires du CEC"},
      {q: "Quelles sont les conditions d'admission à la Faculté de Langues ?", t: " Conditions d'admission"},
      {q: "Quelles licences et programmes techniques offre la Faculté de Langues ?", t: "🏛️ Licences et TSU"}
    ]
  }
};

async function welcome(){
  const L = langPref === 'auto' ? 'es' : langPref;
  const t = TEXTOS[L] || TEXTOS.es;
  
  // Obtener FAQs dinámicas si existen
  let opts = t.sugerencias;
  try {
    const d = await (await fetch('/api/topfaq')).json();
    if (d && d.length) {
      opts = d.map(x => ({q: x.q, t: "🔥 " + (x.q.length > 40 ? x.q.slice(0,40) + "…" : x.q)}));
    }
  } catch(e) {}
  
  const d = document.createElement('div'); d.className = 'msg bot';
  d.innerHTML = '<div class="bub">' + t.bienvenida + '<div class="opts">'
    + opts.map(o => '<button data-q="' + esc(o.q) + '">' + esc(o.t) + '</button>').join('')
    + '</div><span class="nota">' + t.nota + '</span></div>';
  chat.appendChild(d);
  d.querySelectorAll('[data-q]').forEach(b => b.onclick = () => send(b.dataset.q));
  
  // Reproducir audio de bienvenida
  try {
    const audioResp = await fetch('/api/tts?lang=' + L + '&texto=' + encodeURIComponent(t.bienvenida.replace(/<[^>]*>/g, '')));
    const audioData = await audioResp.json();
    if (audioData.url) {
      const au = document.createElement('audio');
      au.controls = true;
      au.src = audioData.url;
      d.querySelector('.bub').appendChild(au);
    }
  } catch(e) {}
  
  chat.scrollTop = chat.scrollHeight;
}

function thinking(){
  removeThink();
  const d = document.createElement('div'); d.className = 'msg bot think'; d.id = 'think';
  d.innerHTML = '<div class="bub">🤔 Trabajando en tu respuesta… <span id="tsec">0</span> s</div>';
  chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  thinkSec = 0;
  thinkTimer = setInterval(() => { thinkSec++; const e = document.getElementById('tsec'); if (e) e.textContent = thinkSec; }, 1000);
}
function removeThink(){
  if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null; }
  const t = document.getElementById('think'); if (t) t.remove();
}
function refreshWho(){
  document.getElementById('who').innerText = currentUser ? '✅ Sesión: ' + currentUser + ' (tus conversaciones se guardan)' : '👋 Modo invitado: sin memoria de conversaciones.';
}
function saveConv(){
  if (!currentUser) return;
  const titulo = ((hist.find(m => m.role === 'user') || {}).content || 'Nueva conversación').slice(0, 40);
  fetch('/api/conv/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: currentId, user: currentUser, titulo, msgs: hist})}).then(() => loadList());
}
async function loadList(){
  if (!currentUser) {
    const msg = '<small>👋 Invitado: sin memoria. Regístrate con  para guardar tus conversaciones.</small>';
    document.getElementById('lista').innerHTML = msg;
    document.getElementById('lista2').innerHTML = msg;
    return;
  }
  const d = await (await fetch('/api/conv/list?user=' + encodeURIComponent(currentUser))).json();
  const html = d.map(c => '<button class="item" data-id="' + c.id + '">' + esc(c.titulo) + '</button>').join('');
  document.getElementById('lista').innerHTML = html || '<small>Sin conversaciones aún.</small>';
  document.getElementById('lista2').innerHTML = html || '<small>Sin conversaciones aún.</small>';
  document.querySelectorAll('[data-id]').forEach(b => b.onclick = () => openConv(b.dataset.id));
}
async function openConv(id){
  const d = await (await fetch('/api/conv/get?id=' + id)).json();
  if (!d.msgs) return;
  currentId = id; hist = d.msgs; state = {pending:false, active:false};
  chat.innerHTML = '';
  hist.forEach(m => bubble(m.role, m.content, m.audio));
  document.getElementById('cdrawer').style.display = 'none';
}
function nueva(){
  currentId = uid(); hist = []; state = {pending:false, active:false};
  chat.innerHTML = ''; welcome(); loadList();
  document.getElementById('cdrawer').style.display = 'none';
}
async function send(msg){
  if (!msg.trim()) return;
  const esClave = state.pending;
  const el = bubble('user', msg);
  hist.push({role:'user', content: esClave ? '••••••' : msg});
  if (esClave) setTimeout(() => { el.querySelector('.bub').textContent = '🔑 ••••••'; }, 30000);
  inp.value = '';
  lastPregunta = msg;
  thinking();
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg, hist: hist.slice(-7), state, lang: langPref})});
  const d = await r.json(); removeThink(); state = d.state;
  lastRespuesta = d.reply;
  hist.push({role:'assistant', content: d.reply, audio: d.audio}); bubble('bot', d.reply, d.audio);
  saveConv();
}
async function loadDocs(){
  const d = await (await fetch('/api/docs')).json();
  document.getElementById('dlist').innerText = (d.docs || []).join('\\n') || 'Sin documentos.';
}

// CAMBIO DE IDIOMA
function applyLang(newLang){
  langPref = newLang;
  document.querySelectorAll('.langs button').forEach(b => b.classList.remove('on'));
  document.getElementById('L' + (newLang === 'auto' ? 'auto' : newLang)).classList.add('on');
  chat.innerHTML = '';
  welcome();
}

document.getElementById('send').onclick = () => send(inp.value);
inp.onkeydown = e => { if (e.key === 'Enter') send(inp.value); };
document.getElementById('nuevo').onclick = nueva;
document.getElementById('nueva').onclick = nueva;
document.getElementById('convs').onclick = () => { const d = document.getElementById('cdrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; loadList(); };
document.getElementById('user').onclick = () => { const d = document.getElementById('udrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; refreshWho(); };
document.getElementById('fb').onclick = () => {
  if (!lastRespuesta) { avisar('️ Aún no hay respuestas que reportar.', 'error'); return; }
  const d = document.getElementById('fbdrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block';
};
document.getElementById('fbsend').onclick = async () => {
  await fetch('/api/feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({pregunta: lastPregunta, respuesta: lastRespuesta, comentario: document.getElementById('fbcom').value, area: document.getElementById('fbarea').value})});
  document.getElementById('fbcom').value = '';
  document.getElementById('fbdrawer').style.display = 'none';
  avisar('📨 Gracias: tu reporte llegó al responsable del área y alimentará al bot.', 'ok');
};
document.getElementById('ureg').onclick = async () => {
  const d = await (await fetch('/api/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar('✅ Bienvenido, ' + currentUser + '. Tus conversaciones se guardarán.', 'ok');
};
document.getElementById('ulin').onclick = async () => {
  const d = await (await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar('✅ Sesión iniciada: ' + currentUser, 'ok');
};
document.getElementById('uguest').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; };
document.getElementById('uout').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; avisar('👋 Sesión cerrada.'); };

// BOTONES DE IDIOMA
[['auto','auto'],['es','es'],['en','en'],['fr','fr']].forEach(([id, val]) => {
  document.getElementById('L' + id).onclick = () => applyLang(val);
});

// TAMAÑO DE LETRA
document.getElementById('fmas').onclick = () => {
  fontScale = Math.min(2.0, fontScale + 0.1);
  document.documentElement.style.setProperty('--fs', fontScale);
  avisar(' Letra: ' + Math.round(fontScale * 100) + '%', 'ok');
};
document.getElementById('fmenos').onclick = () => {
  fontScale = Math.max(0.8, fontScale - 0.1);
  document.documentElement.style.setProperty('--fs', fontScale);
  avisar('🔍 Letra: ' + Math.round(fontScale * 100) + '%', 'ok');
};

// PANTALLA COMPLETA
document.getElementById('full').onclick = () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
};

const drop = document.getElementById('drop');
function marcarArchivo(f){
  droppedFile = f;
  drop.innerHTML = '📎 ' + esc(f.name);
  avisar('📎 Archivo listo: ' + f.name + ' → pulsa "📤 Subir y publicar".');
}
drop.onclick = () => document.getElementById('ffile').click();
drop.ondragover = e => e.preventDefault();
drop.ondrop = e => { e.preventDefault(); if (e.dataTransfer.files[0]) marcarArchivo(e.dataTransfer.files[0]); };
document.getElementById('ffile').onchange = e => { if (e.target.files[0]) marcarArchivo(e.target.files[0]); };
const mic = document.getElementById('mic');
mic.onclick = async () => {
  if (rec && rec.state === 'recording') { rec.stop(); return; }
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  chunks = []; rec = new MediaRecorder(stream);
  rec.ondataavailable = e => chunks.push(e.data);
  rec.onstop = async () => {
    stream.getTracks().forEach(t => t.stop()); mic.classList.remove('rec');
    thinking();
    const fd = new FormData();
    fd.append('audio', new Blob(chunks, {type:'audio/webm'}), 'voz.webm');
    fd.append('hist', JSON.stringify(hist.slice(-7)));
    fd.append('state', JSON.stringify(state));
    fd.append('lang', langPref);
    const d = await (await fetch('/api/voice', {method:'POST', body: fd})).json();
    removeThink(); state = d.state;
    if (d.texto) { bubble('user', '🎤 ' + d.texto); hist.push({role:'user', content: d.texto}); lastPregunta = d.texto; }
    if (d.reply) { bubble('bot', d.reply, d.audio); hist.push({role:'assistant', content: d.reply, audio: d.audio}); lastRespuesta = d.reply; }
    saveConv();
  };
  rec.start(); mic.classList.add('rec');
  avisar('🎤 Grabando tu pregunta… toca el micrófono para terminar.');
};
document.getElementById('gear').onclick = () => { const d = document.getElementById('drawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; };
document.getElementById('salirp').onclick = () => { state = {pending:false, active:false}; document.getElementById('drawer').style.display = 'none'; document.getElementById('zona').style.display = 'none'; };
document.getElementById('clave').onkeydown = e => { if (e.key === 'Enter') document.getElementById('unlock').click(); };
document.getElementById('fdel').onkeydown = e => { if (e.key === 'Enter') document.getElementById('bdel').click(); };
document.getElementById('unlock').onclick = async () => {
  const r = await fetch('/api/unlock', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})});
  const d = await r.json();
  document.getElementById('zona').style.display = d.ok ? 'block' : 'none';
  if (d.ok) { loadDocs(); avisar('✅ Panel de personal abierto.', 'ok'); }
  else avisar('❌ Clave incorrecta.', 'error');
};
document.getElementById('fsubir').onclick = async () => {
  const f = document.getElementById('ffile').files[0] || droppedFile;
  if (!f && !document.getElementById('ftexto').value.trim()) { avisar('⚠️ Elige un archivo o pega el texto del aviso en el cuadro 📝.', 'error'); return; }
  avisar(' Procesando y publicando… puede tardar unos segundos.');
  const fd = new FormData();
  if (f) fd.append('archivo', f);
  fd.append('categoria', document.getElementById('fcat').value);
  fd.append('vigencia', document.getElementById('fvig').value);
  fd.append('reemplazar', '0');
  fd.append('texto_manual', document.getElementById('ftexto').value);
  const d = await (await fetch('/api/upload', {method:'POST', body: fd})).json();
  document.getElementById('fest').innerText = d.estado;
  avisar(d.estado, d.estado.startsWith('✅') ? 'ok' : 'error');
  loadDocs();
};
document.getElementById('ldocs').onclick = loadDocs;
document.getElementById('lfb').onclick = async () => {
  const d = await (await fetch('/api/feedback/list?clave=' + encodeURIComponent(document.getElementById('clave').value))).json();
  document.getElementById('fest').innerText = (d.items || []).join('\\n------------------\\n');
  avisar('📨 Feedbacks listados abajo.', 'ok');
};
document.getElementById('bdel').onclick = async () => {
  const d = await (await fetch('/api/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value, nombre: document.getElementById('fdel').value})})).json();
  document.getElementById('fest').innerText = d.estado;
  avisar(d.estado, d.estado.startsWith('🗑️') ? 'ok' : 'error');
  loadDocs();
};
document.getElementById('nota').onclick = async () => {
  if (rec2 && rec2.state === 'recording') { rec2.stop(); return; }
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  let ch = []; rec2 = new MediaRecorder(stream);
  rec2.ondataavailable = e => ch.push(e.data);
  rec2.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    avisar('⏳ Transcribiendo y publicando tu nota…');
    const fd = new FormData();
    fd.append('audio', new Blob(ch, {type:'audio/webm'}), 'nota.webm');
    fd.append('categoria', document.getElementById('fcat').value);
    const d = await (await fetch('/api/voice_note', {method:'POST', body: fd})).json();
    document.getElementById('fest').innerText = d.estado;
    avisar(d.estado, d.estado.startsWith('✅') ? 'ok' : 'error');
    loadDocs();
  };
  rec2.start();
  avisar('🔴 Grabando nota… toca de nuevo para terminar y publicar.');
};
document.getElementById('rep').onclick = async () => {
  const d = await (await fetch('/api/report', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})})).json();
  if (d.error) { avisar(d.error, 'error'); return; }
  document.getElementById('fest').innerText = '📊 Total: ' + d.total + ' · Hoy: ' + d.hoy + ' · Idiomas: ' + JSON.stringify(d.idiomas)
    + '\\n\\n🔥 Más frecuentes:\\n' + d.top.map((x, i) => (i+1) + '. ' + x[0] + ' (' + x[1] + ')').join('\\n');
  avisar('📊 Reporte listo en el panel.', 'ok');
};
welcome(); loadList(); refreshWho(); inp.focus();
</script>
</body>
</html>
"""
