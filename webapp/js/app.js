const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const store = {
  get(k, d) { try { const v = JSON.parse(localStorage.getItem('pk_' + k)); return v == null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('pk_' + k, JSON.stringify(v)); } catch (e) {} },
};
const alertMsg = (m) => (tg && tg.showAlert ? tg.showAlert(m) : alert(m));

const NAV = [['home', '🏠', 'Главная'], ['mentor', '🤖', 'Наставник'], ['curriculum', '📚', 'Программа'], ['practice', '✍️', 'Практика'], ['progress', '📈', 'Прогресс']];
const PARENT = { topic: 'curriculum', task: 'practice', quiz: 'practice', materials: 'home', support: 'home' };
const MODES = {
  mentor: ['💬 Вопрос', 'Задай вопрос по информатике или программированию…'],
  review: ['🐞 Разбор кода', 'Вставь код и опиши, что не работает…'],
  check: ['🧠 Проверь меня', 'Напиши тему, по которой нужна проверка…'],
};
const GRADES = ['8 класс', '9 класс', '10 класс', '11 класс', 'Абитуриент'];
const LEVELS = [[1, 'Начальный'], [2, 'Средний'], [3, 'Продвинутый']];
const LANGS = ['C++', 'Python', 'Java', 'C#', 'JavaScript', 'Pascal'];

let C = { topics: [] };
const S = {
  view: 'home', arg: null, mode: 'mentor', chat: [], busy: false, pending: null,
  profile: store.get('profile', { grade: '10 класс', level: 1, language: 'C++' }),
  progress: store.get('progress', { learned: {}, tasks: {}, quiz: {} }),
};
const save = () => { store.set('profile', S.profile); store.set('progress', S.progress); };
const topic = (id) => C.topics.find((t) => t.id === id);
const allTasks = () => C.topics.flatMap((t) => t.tasks.map((k) => Object.assign({ topic: t.id }, k)));
const taskById = (id) => allTasks().find((k) => k.id === id);
const ts = (id) => (S.progress.tasks[id] = S.progress.tasks[id] || { hints: 0, aiHints: 0, code: '', outline: false, solved: false });
const nextTopic = () => C.topics.find((t) => !S.progress.learned[t.id] && t.level <= S.profile.level) || C.topics.find((t) => !S.progress.learned[t.id]);

async function api(path, body) {
  const r = await fetch('/api/' + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({}, body, { initData: (tg && tg.initData) || '' })),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || 'Ошибка сети');
  return j;
}

function md(t) {
  return String(t).split('```').map((p, i) => i % 2
    ? '<pre><code>' + esc(p.replace(/^[a-zA-Z+#]*\n/, '')) + '</code></pre>'
    : esc(p).replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>')).join('');
}

const card = (v, ic, t, s) => `<button class="card" data-act="go" data-v="${v}"><div class="ic">${ic}</div><b>${t}</b><small>${s}</small></button>`;
const sel = (key, opts) => `<select data-profile="${key}">${opts.map(([v, l]) => `<option value="${v}" ${String(S.profile[key]) === String(v) ? 'selected' : ''}>${l}</option>`).join('')}</select>`;

const VIEWS = {
  home() {
    const n = tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.first_name;
    return `<section class="hero"><span class="badge">Бета-версия</span><h1>Привет${n ? ', ' + esc(n) : ''}! 👋</h1>
<p>Учись понимать информатику и программирование, а не копировать ответы.</p>
<button class="btn" data-act="start">🚀 ${S.progress.started ? 'Продолжить' : 'Начать'} обучение</button></section>
<div class="grid">${card('mentor', '🤖', 'ИИ-наставник', 'Объяснит и подскажет')}${card('curriculum', '📚', 'Учебная программа', 'Темы по уровням')}${card('progress', '📈', 'Мой прогресс', 'Результаты')}${card('practice', '✍️', 'Практика', 'Задачи и тесты')}${card('materials', '📖', 'Материалы', 'Учебники и поиск')}${card('support', '⭐', 'Поддержать', 'Telegram Stars')}</div>
<p class="note">Экспериментальный проект для Осенней школы абитуриентов Института бизнеса БГУ. Проект в разработке и не является официальным продуктом БГУ.</p>`;
  },
  mentor() {
    return `<h2>🤖 ИИ-наставник <span class="badge">Бета</span></h2>
<div class="chips">${Object.entries(MODES).map(([k, v]) => `<button class="chip ${S.mode === k ? 'on' : ''}" data-act="mode" data-m="${k}">${v[0]}</button>`).join('')}<button class="chip" data-act="reset">🗑 Новый диалог</button></div>
<div id="msgs"></div>
<div class="composer"><textarea id="inp" rows="2" placeholder="${esc(MODES[S.mode][1])}"></textarea><button class="send" data-act="send">➤</button></div>
<p class="note">ИИ может ошибаться — проверяй важное. Он подсказывает, а не решает за тебя.</p>`;
  },
  curriculum() {
    const list = C.topics.slice().sort((a, b) => a.level - b.level);
    return `<h2>📚 Учебная программа</h2><div class="box"><small class="muted">Подстрой обучение под себя</small>
${sel('grade', GRADES.map((g) => [g, g]))}${sel('level', LEVELS)}${sel('language', LANGS.map((l) => [l, l]))}</div>
${list.map((t) => `<button class="row" data-act="go" data-v="topic" data-a="${t.id}"><span>${S.progress.learned[t.id] ? '✅' : '⬜'}</span><div><b>${esc(t.title)}</b><small>Уровень ${t.level}${t.level > S.profile.level ? ' · сложнее твоего уровня' : ''}</small></div></button>`).join('')}`;
  },
  topic(id) {
    const t = topic(id); if (!t) return '<p class="err">Тема не найдена.</p>';
    return `<h2>${esc(t.title)}</h2><p class="muted">Уровень ${t.level}. ${esc(t.summary)}</p>
<div class="box"><ul>${t.points.map((p) => `<li>${esc(p)}</li>`).join('')}</ul></div>
<button class="btn" data-act="explain" data-t="${id}">🤖 Объясни мне тему</button>
<button class="btn alt" data-act="go" data-v="task" data-a="${t.tasks[0].id}">✍️ Задача по теме</button>
<button class="btn alt" data-act="go" data-v="quiz" data-a="${id}">🧠 Тест по теме</button>
<button class="btn alt" data-act="learned" data-t="${id}">${S.progress.learned[id] ? '✅ Изучена — снять отметку' : 'Отметить изученной'}</button>`;
  },
  practice() {
    return `<h2>✍️ Практика</h2><h3>Задачи</h3>${allTasks().map((k) => `<button class="row" data-act="go" data-v="task" data-a="${k.id}"><span>${(S.progress.tasks[k.id] || {}).solved ? '✅' : '📝'}</span><div><b>${esc(k.title)}</b><small>${esc(topic(k.topic).title)}</small></div></button>`).join('')}
<h3>Тесты</h3>${C.topics.map((t) => { const q = S.progress.quiz[t.id] || {}; const n = Object.keys(q).length; return `<button class="row" data-act="go" data-v="quiz" data-a="${t.id}"><span>🧠</span><div><b>${esc(t.title)}</b><small>${n}/${t.quiz.length} отвечено</small></div></button>`; }).join('')}`;
  },
  task(id) {
    const k = taskById(id); if (!k) return '<p class="err">Задача не найдена.</p>'; const st = ts(id);
    return `<h2>${esc(k.title)}</h2><div class="box">${esc(k.text)}</div>
${k.hints.slice(0, st.hints).map((h, i) => `<div class="hint">💡 ${i + 1}. ${esc(h)}</div>`).join('')}
${st.hints < k.hints.length ? `<button class="btn alt" data-act="hint" data-id="${id}">💡 Показать подсказку (${st.hints}/${k.hints.length})</button>` : ''}
<button class="btn alt" data-act="aihint" data-id="${id}">🤖 Подсказка от наставника</button>
<textarea data-code="${id}" placeholder="Твоё решение: код или описание алгоритма…">${esc(st.code || '')}</textarea>
<button class="btn" data-act="review" data-id="${id}">🔍 Разобрать моё решение</button>
<button class="btn alt" data-act="outline" data-id="${id}">📖 Показать разбор</button>
${st.outline ? `<div class="box"><b>Разбор</b><br>${esc(k.outline)}</div>` : '<p class="note">Разбор доступен после попытки решения.</p>'}
<button class="btn alt" data-act="solved" data-id="${id}">${st.solved ? '✅ Решена — снять отметку' : 'Отметить решённой'}</button>`;
  },
  quiz(id) {
    const t = topic(id); if (!t) return '<p class="err">Тест не найден.</p>'; const q = S.progress.quiz[id] || {};
    return `<h2>🧠 Тест: ${esc(t.title)}</h2>` + t.quiz.map((x, i) => {
      const a = q[i];
      return `<div class="box"><b>${i + 1}. ${esc(x.q)}</b>${x.options.map((o, j) => `<button class="opt ${a ? (j === x.answer ? 'ok' : j === a.o ? 'bad' : '') : ''}" ${a ? 'disabled' : ''} data-act="ans" data-t="${id}" data-q="${i}" data-o="${j}">${esc(o)}</button>`).join('')}${a ? `<p class="muted">${a.ok ? '✅ Верно. ' : '❌ Не совсем. '}${esc(x.why)}</p>` : ''}</div>`;
    }).join('') + `<button class="btn alt" data-act="retry" data-t="${id}">Пройти заново</button>`;
  },
  progress() {
    const T = C.topics, L = T.filter((t) => S.progress.learned[t.id]).length;
    const K = allTasks(), solved = K.filter((k) => (S.progress.tasks[k.id] || {}).solved).length;
    let qa = 0, qok = 0; const weak = [];
    T.forEach((t) => { const q = S.progress.quiz[t.id] || {}; const v = Object.values(q); qa += v.length; const ok = v.filter((x) => x.ok).length; qok += ok; if (v.length && ok / v.length < 0.7) weak.push(t); });
    const recs = [];
    const nt = nextTopic(); if (nt) recs.push(`<button class="row" data-act="go" data-v="topic" data-a="${nt.id}"><span>➡️</span><div><b>Следующая тема: ${esc(nt.title)}</b></div></button>`);
    weak.forEach((t) => recs.push(`<button class="row" data-act="go" data-v="topic" data-a="${t.id}"><span>🔁</span><div><b>Повтори: ${esc(t.title)}</b><small>В тесте меньше 70% верных</small></div></button>`));
    K.filter((k) => S.progress.learned[k.topic] && !(S.progress.tasks[k.id] || {}).solved).slice(0, 2).forEach((k) => recs.push(`<button class="row" data-act="go" data-v="task" data-a="${k.id}"><span>✍️</span><div><b>Попробуй задачу: ${esc(k.title)}</b></div></button>`));
    return `<h2>📈 Мой прогресс</h2><div class="box"><b>Изучено тем: ${L} из ${T.length}</b><div class="bar"><i style="width:${T.length ? (100 * L / T.length) : 0}%"></i></div></div>
<div class="box">Решено задач: <b>${solved} из ${K.length}</b><br>Верных ответов в тестах: <b>${qok} из ${qa}</b></div>
<h3>Рекомендации</h3>${recs.join('') || '<p class="muted">Всё выполнено — отличная работа! 🎉</p>'}
<p class="note">Прогресс хранится на этом устройстве и не синхронизируется.</p>
<button class="btn alt" data-act="wipe">Сбросить прогресс</button>`;
  },
  materials() {
    return `<h2>📖 Материалы <span class="badge">Бета</span></h2><textarea id="q" rows="1" style="min-height:44px;font-family:inherit" placeholder="Поиск по материалам…"></textarea>
<button class="btn alt" data-act="msearch">🔎 Найти</button><div id="mat"><p class="muted">Загрузка…</p></div>`;
  },
  support() {
    return `<h2>⭐ Поддержать проект</h2><p class="muted">Добровольный донат через Telegram Stars. Проект в бета-версии — спасибо за поддержку! 💙</p>
${[50, 100, 250].map((a) => `<button class="btn alt" data-act="donate" data-a="${a}">⭐ ${a}</button>`).join('')}<p id="dmsg" class="note"></p>`;
  },
};

function renderChat() {
  const box = $('#msgs'); if (!box) return;
  const hello = '<div class="msg">Привет! Я наставник «Понял.Код». Помогу разобраться с темой, ошибкой или задачей — подсказками, а не готовыми ответами.</div>';
  box.innerHTML = hello + S.chat.map((m) => `<div class="msg ${m.r === 'u' ? 'u' : ''} ${m.err ? 'err' : ''}">${md(m.t)}${m.src && m.src.length ? `<br><small>Источники: ${esc(m.src.join(', '))}</small>` : ''}</div>`).join('') + (S.busy ? '<div class="msg muted">Наставник думает…</div>' : '');
  window.scrollTo(0, document.body.scrollHeight);
}

async function send(p) {
  S.chat.push({ r: 'u', t: p.display || p.text }); S.busy = true; renderChat();
  try {
    const j = await api('chat', { message: p.text, mode: p.mode || S.mode, profile: S.profile, taskId: p.taskId, hintLevel: p.hintLevel });
    S.chat.push({ r: 'a', t: j.answer, src: j.sources });
  } catch (e) { S.chat.push({ r: 'a', t: e.message, err: true }); }
  S.busy = false; renderChat();
}
function askMentor(p) { S.pending = p; go('mentor'); }

async function loadMaterials(q) {
  const box = $('#mat'); if (!box) return;
  try {
    const j = await api('materials', { query: q || '' });
    const res = q ? (j.results.length ? j.results.map((r) => `<div class="box"><small>${esc(r.source)}</small><p>${esc(r.text)}</p></div>`).join('') : '<p class="muted">Ничего не найдено.</p>') : '';
    box.innerHTML = res + (j.files.length ? '<p>Загружено файлов:</p><ul>' + j.files.map((f) => `<li>${esc(f)}</li>`).join('') + '</ul>' : '<p class="muted">Материалы пока не добавлены — скоро появятся.</p>');
  } catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
}

function go(view, arg) { S.view = view; S.arg = arg == null ? null : arg; render(); window.scrollTo(0, 0); }
function render() {
  $('#app').innerHTML = VIEWS[S.view](S.arg);
  const cur = PARENT[S.view] === 'home' ? 'home' : (PARENT[S.view] || S.view);
  $('#nav').innerHTML = NAV.map(([v, i, l]) => `<button class="${v === cur ? 'on' : ''}" data-act="go" data-v="${v}"><span>${i}</span>${l}</button>`).join('');
  if (tg && tg.BackButton) { PARENT[S.view] ? tg.BackButton.show() : tg.BackButton.hide(); }
  if (S.view === 'mentor') { renderChat(); if (S.pending) { const p = S.pending; S.pending = null; send(p); } }
  if (S.view === 'materials') loadMaterials('');
}

const ACTS = {
  go: (d) => go(d.v, d.a),
  start() { S.progress.started = true; save(); const t = nextTopic(); t ? go('topic', t.id) : go('curriculum'); },
  mode(d) { S.mode = d.m; render(); },
  async reset() { S.chat = []; renderChat(); try { await api('reset', {}); } catch (e) {} },
  send() { const i = $('#inp'); const text = i.value.trim(); if (!text || S.busy) return; i.value = ''; send({ text }); },
  explain(d) { const t = topic(d.t); askMentor({ text: 'Объясни тему: ' + t.title, display: 'Объясни тему: ' + t.title, mode: 'explain' }); },
  learned(d) { S.progress.learned[d.t] = !S.progress.learned[d.t]; save(); render(); },
  hint(d) { const s = ts(d.id), k = taskById(d.id); if (s.hints < k.hints.length) s.hints++; save(); render(); },
  aihint(d) { const s = ts(d.id), k = taskById(d.id); s.aiHints = Math.min((s.aiHints || 0) + 1, 3); save(); askMentor({ text: 'Дай подсказку к задаче «' + k.title + '»', mode: 'hint', taskId: d.id, hintLevel: s.aiHints }); },
  review(d) {
    const k = taskById(d.id), code = ($('[data-code]').value || '').trim();
    if (code.length < 10) return alertMsg('Сначала напиши своё решение.');
    askMentor({ text: code, display: 'Разбери моё решение задачи «' + k.title + '»:\n```\n' + code + '\n```', mode: 'review', taskId: d.id });
  },
  outline(d) { const s = ts(d.id); if ((s.code || '').trim().length < 20) return alertMsg('Сначала попробуй решить задачу самостоятельно — тогда откроется разбор.'); s.outline = true; save(); render(); },
  solved(d) { const s = ts(d.id); s.solved = !s.solved; save(); render(); },
  ans(d) {
    const x = topic(d.t).quiz[+d.q], q = (S.progress.quiz[d.t] = S.progress.quiz[d.t] || {});
    if (q[d.q]) return; q[d.q] = { o: +d.o, ok: +d.o === x.answer }; save(); render();
  },
  retry(d) { delete S.progress.quiz[d.t]; save(); render(); },
  wipe() { if (confirm('Сбросить весь прогресс на этом устройстве?')) { S.progress = { learned: {}, tasks: {}, quiz: {} }; save(); render(); } },
  msearch() { loadMaterials(($('#q').value || '').trim()); },
  async donate(d) {
    const m = $('#dmsg');
    if (!(tg && tg.openInvoice)) { m.textContent = 'Открой приложение внутри Telegram.'; return; }
    try {
      const j = await api('donate', { amount: +d.a });
      tg.openInvoice(j.url, (s) => { m.textContent = s === 'paid' ? 'Спасибо за поддержку! 💙' : s === 'cancelled' ? 'Оплата отменена.' : s === 'failed' ? 'Оплата не прошла.' : ''; });
    } catch (e) { m.textContent = e.message; }
  },
};

document.addEventListener('click', (e) => { const el = e.target.closest('[data-act]'); if (el && ACTS[el.dataset.act]) ACTS[el.dataset.act](el.dataset, el); });
document.addEventListener('change', (e) => { const k = e.target.dataset && e.target.dataset.profile; if (k) { S.profile[k] = k === 'level' ? +e.target.value : e.target.value; save(); render(); } });
document.addEventListener('input', (e) => { const id = e.target.dataset && e.target.dataset.code; if (id) { ts(id).code = e.target.value; save(); } });
if (tg && tg.BackButton) tg.BackButton.onClick(() => { const p = PARENT[S.view]; if (p) go(p); });

(async () => {
  try { C = await (await fetch('/api/curriculum')).json(); }
  catch (e) { $('#app').innerHTML = '<p class="err">Не удалось загрузить программу. Обнови страницу.</p>'; return; }
  render();
})();
