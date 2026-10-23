"use strict";

// ------------------------------------------------------------------ utilitaires
const $ = (sel) => document.querySelector(sel);

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* stockage indisponible */ }
  },
};

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    let msg = resp.statusText;
    try { msg = (await resp.json()).error || msg; } catch { /* corps non JSON */ }
    throw new Error(msg);
  }
  return resp;
}

const postJson = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

function parseDate(s) {
  if (!s) return null;
  const d = new Date(s.includes("T") ? s : s.replace(" ", "T") + "Z"); // SQLite = UTC
  return isNaN(d) ? null : d;
}

function dayLabel(d) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const that = new Date(d); that.setHours(0, 0, 0, 0);
  const diff = Math.round((today - that) / 86400000);
  if (diff === 0) return "Aujourd'hui";
  if (diff === 1) return "Hier";
  return d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
}

// ------------------------------------------------------------------ « déjà vu » (synchronisé serveur)
const seenIds = new Set();
function markSeen(id) {
  if (!id || seenIds.has(id)) return;
  seenIds.add(id);
  document.querySelectorAll(`[data-card="${id}"]`).forEach((c) => c.classList.add("seen"));
  postJson("/api/seen", { ids: [id] }).then(refreshFlashCount).catch(() => {});
}

// ------------------------------------------------------------------ réglages voix
const settings = {
  speed: store.get("xena-speed", 0.9),
  voice: store.get("xena-voice", "gemini"),
};

function initSettings() {
  const speed = $("#speed"), out = $("#speed-out"), mode = $("#voice-mode");
  speed.value = settings.speed;
  out.textContent = Number(settings.speed).toFixed(2) + "×";
  mode.value = settings.voice;
  speed.addEventListener("input", () => {
    settings.speed = Number(speed.value);
    out.textContent = settings.speed.toFixed(2) + "×";
    store.set("xena-speed", settings.speed);
    applyRate();
  });
  mode.addEventListener("change", () => { settings.voice = mode.value; store.set("xena-voice", mode.value); });
  $("#settings-btn").addEventListener("click", () => {
    $("#settings").hidden = !$("#settings").hidden;
    if (!$("#settings").hidden) loadReglages();
  });
  $("#r-save").addEventListener("click", saveReglages);
}

// Réglages de Xena (en base, côté serveur) : composants critiques, questions négatives, profil, contradicteur
const REGLAGES = ["composants_critiques", "questions_negatives", "profil"];

async function loadReglages() {
  try {
    const r = await (await api("/api/reglages")).json();
    for (const name of REGLAGES) $(`#r-${name}`).value = r[name] || "";
    $("#r-contradicteur").checked = !!r.contradicteur;
    $("#r-seuil_push").value = r.seuil_push || "exceptionnel";
    refreshPush();
    $("#r-status").textContent = "";
  } catch (e) { $("#r-status").textContent = "⚠ " + e.message; }
}

async function saveReglages() {
  const body = { contradicteur: $("#r-contradicteur").checked };
  for (const name of REGLAGES) body[name] = $(`#r-${name}`).value;
  body.seuil_push = $("#r-seuil_push").value;
  try {
    await postJson("/api/reglages", body);
    $("#r-status").textContent = "✓";
  } catch (e) { $("#r-status").textContent = "⚠ " + e.message; }
}

// ------------------------------------------------------------------ lecteur : une file d'écoute unique
// Sert au résumé d'un article, au flash « Ce que j'ai raté » et aux réponses de Xena.
// Un seul élément <audio> réutilisé : Safari n'autorise la lecture qu'après un premier geste.
const player = $("#player");
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
let audioUnlocked = false;

function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  player.src = SILENCE;
  player.play().catch(() => {});
  if (window.speechSynthesis) speechSynthesis.speak(new SpeechSynthesisUtterance(""));
}

function applyRate() {
  player.defaultPlaybackRate = settings.speed;
  player.playbackRate = settings.speed;
  player.preservesPitch = true;
  player.webkitPreservesPitch = true;
}
player.addEventListener("loadedmetadata", applyRate);

const queue = { items: [], index: -1, kind: null, token: 0, blobs: new Map(), url: null };

function loadItem(i) {
  if (!queue.blobs.has(i)) {
    const p = queue.items[i].load();
    p.catch(() => {});
    queue.blobs.set(i, p);
  }
  return queue.blobs.get(i);
}

// items : [{ kicker, label, article, load: () => Promise<Blob>, onStart }]
function playQueue(items, kind) {
  stopAll();
  unlockAudio();
  queue.items = items;
  queue.kind = kind;
  queue.blobs = new Map();
  $("#player-bar").hidden = false;
  $("#p-dig").hidden = kind === "chat";
  $("#player-kicker").hidden = items.length < 2 || kind === "chat";
  $("#p-prev").hidden = $("#p-next").hidden = items.length < 2;
  playIndex(0);
}

async function playIndex(i) {
  if (i < 0 || i >= queue.items.length) return finishQueue();
  const token = ++queue.token;
  queue.index = i;
  const item = queue.items[i];
  $("#player-kicker").textContent = item.kicker || "";
  $("#player-label").textContent = item.label || "";
  $("#progress-fill").style.width = "0%";
  player.pause();
  $("#p-toggle").textContent = "⏳";
  let blob;
  try {
    blob = await loadItem(i);
  } catch (e) {
    if (token !== queue.token) return;
    $("#player-label").textContent = "⚠ " + e.message;
    return setTimeout(() => token === queue.token && playIndex(i + 1), 1500);
  }
  if (token !== queue.token) return;
  if (i + 1 < queue.items.length) loadItem(i + 1); // le suivant se prépare pendant l'écoute
  if (queue.url) URL.revokeObjectURL(queue.url);
  queue.url = URL.createObjectURL(blob);
  player.src = queue.url;
  applyRate();
  item.onStart?.();
  player.play().catch(() => { $("#p-toggle").textContent = "▶"; });
}

player.addEventListener("ended", () => {
  if (queue.index < 0) return;
  const token = queue.token;
  // Respiration entre deux segments
  setTimeout(() => token === queue.token && playIndex(queue.index + 1), queue.kind === "chat" ? 300 : 900);
});
player.addEventListener("timeupdate", () => {
  if (player.duration) $("#progress-fill").style.width = (100 * player.currentTime / player.duration) + "%";
});
player.addEventListener("pause", () => { $("#p-toggle").textContent = "▶"; });
player.addEventListener("play", () => { $("#p-toggle").textContent = "⏸"; });

function finishQueue() {
  queue.token++;
  queue.index = -1;
  queue.items = [];
  queue.kind = null;
  player.pause();
  $("#player-bar").hidden = true;
  highlight(-1);
}

function stopAll() {
  finishQueue();
  if (window.speechSynthesis) speechSynthesis.cancel();
}

$("#p-toggle").addEventListener("click", () => {
  if (queue.index < 0) return;
  if (player.paused) player.play().catch(() => {}); else player.pause();
});
$("#p-next").addEventListener("click", () => playIndex(queue.index + 1));
$("#p-prev").addEventListener("click", () => {
  if (player.currentTime > 4) { player.currentTime = 0; return; }
  playIndex(Math.max(0, queue.index - 1));
});
$("#p-close").addEventListener("click", stopAll);
$("#p-dig").addEventListener("click", () => {
  const item = queue.items[queue.index];
  if (!item?.article) return;
  player.pause();
  openChat(item.article);
});

const fetchBlob = (path) => () => api(path).then((r) => r.blob());

function listenArticle(a) {
  markSeen(a.id);
  playQueue([{
    label: a.titre, article: a,
    load: fetchBlob(`/api/articles/${a.id}/audio`),
  }], "article");
}

// ------------------------------------------------------------------ flash « Ce que j'ai raté »
async function refreshFlashCount() {
  try {
    const data = await (await api("/api/flash")).json();
    const n = data.articles.length;
    $("#flash-count").textContent = n || "";
    $("#flash-btn").classList.toggle("empty", !n);
    return data.articles;
  } catch { return []; }
}

async function playFlash() {
  unlockAudio();
  const articles = await refreshFlashCount();
  if (!articles.length) return;
  playQueue(articles.map((a, i) => ({
    kicker: `${i + 1}/${articles.length}`, label: a.titre, article: a,
    load: fetchBlob(`/api/articles/${a.id}/audio?version=court`),
    onStart: () => markSeen(a.id),
  })), "flash");
}

// ------------------------------------------------------------------ fil d'actu
let filtre = store.get("xena-filtre", "top");
let feedState = { offset: 0, lastDay: null, dossiers: new Set() };

function initTabs() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.filtre === filtre);
    t.addEventListener("click", () => {
      filtre = t.dataset.filtre;
      store.set("xena-filtre", filtre);
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
      renderFeed();
    });
  });
}

async function renderFeed() {
  const feed = $("#feed");
  feed.replaceChildren(h("div", { class: "loading" }, "Chargement…"));
  feedState = { offset: 0, lastDay: null, dossiers: new Set() };
  const synth = h("div", {});
  const list = h("div", {});
  const more = h("button", { class: "btn ghost more", onclick: () => loadMore(list, more) }, "Plus de news");
  await Promise.all([loadMore(list, more), loadSynthese(synth)]);
  feed.replaceChildren(synth, list, more);
  if (!list.children.length && !synth.children.length) feed.replaceChildren(h("p", { class: "empty" }, "Rien pour l'instant."));
}

// ------------------------------------------------------------------ notifications push
// iPhone / iPad : seulement depuis l'app ajoutée à l'écran d'accueil (iOS 16.4+), et après un geste.
const push = { reg: null, sub: null, actif: false };
const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const standalone = window.matchMedia?.("(display-mode: standalone)").matches || navigator.standalone === true;
const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

async function initServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  try {
    push.reg = await navigator.serviceWorker.register("/sw.js");
    navigator.serviceWorker.addEventListener("message", (e) => { if (e.data?.open) location.href = e.data.open; });
  } catch { /* pas de service worker : pas de push, le reste marche */ }
}

function b64ToBytes(b64) {
  const s = atob((b64 + "=".repeat((4 - b64.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

async function refreshPush() {
  const state = $("#push-state"), toggle = $("#push-toggle"), test = $("#push-test"), help = $("#push-help");
  help.hidden = true;
  if (!pushSupported() || !push.reg) {
    toggle.hidden = test.hidden = true;
    state.textContent = "indisponibles ici";
    help.hidden = false;
    help.textContent = isIOS && !standalone
      ? "Ajoute d'abord Xena à l'écran d'accueil (Partager → Sur l'écran d'accueil), puis ouvre-la depuis son icône."
      : "Ce navigateur ne gère pas les notifications web.";
    return;
  }
  push.sub = await push.reg.pushManager.getSubscription();
  let actif = false, derniers = [];
  try {
    const r = await (await api("/api/push/status?endpoint=" + encodeURIComponent(push.sub?.endpoint || ""))).json();
    actif = r.actif; derniers = r.derniers || [];
  } catch { /* hors ligne */ }
  actif = actif && Notification.permission === "granted";
  push.actif = actif;
  state.textContent = actif ? "actives sur cet appareil" : Notification.permission === "denied" ? "bloquées dans les réglages de l'appareil" : "désactivées";
  toggle.hidden = Notification.permission === "denied";
  toggle.textContent = actif ? "Désactiver" : "Activer sur cet appareil";
  test.hidden = !actif;
  $("#push-log").replaceChildren(...derniers.slice(0, 5).map((p) =>
    h("li", {}, `${shortDate(p.created_at)} · ${p.titre}`, p.raison ? h("span", {}, " — " + p.raison) : null)));
}

async function togglePush() {
  const state = $("#push-state");
  try {
    if (push.actif) {
      await postJson("/api/push/unsubscribe", { endpoint: push.sub.endpoint });
      await push.sub.unsubscribe();
    } else {
      if (await Notification.requestPermission() !== "granted") return refreshPush();
      const { key } = await (await api("/api/push/key")).json();
      const sub = push.sub || await push.reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
      await postJson("/api/push/subscribe", { subscription: sub.toJSON() });
    }
  } catch (e) { state.textContent = "⚠ " + e.message; return; }
  refreshPush();
}

async function testPush() {
  try {
    await postJson("/api/push/test", { endpoint: push.sub?.endpoint || "" });
    $("#push-state").textContent = "notification envoyée";
  } catch (e) { $("#push-state").textContent = "⚠ " + e.message; }
}

// Une notification ouvre /#a-<id> : la fiche s'affiche en tête du fil
async function openFromHash() {
  const m = location.hash.match(/^#a-([0-9a-f]{16})$/);
  if (!m) return;
  history.replaceState(null, "", location.pathname);
  try {
    const a = await (await api(`/api/articles/${m[1]}`)).json();
    const card = renderCard(a);
    $("#feed").prepend(card);
    card.querySelector(".card-main").click();
    window.scrollTo({ top: 0 });
  } catch { /* article introuvable : on reste sur le fil */ }
}

// ------------------------------------------------------------------ synthèse 12 h
// En tête du fil : la phrase à retenir et l'action ; le détail se déplie. ‹ › parcourt les synthèses précédentes.
async function loadSynthese(box, id) {
  try {
    const resp = await fetch("/api/synthese" + (id ? `?id=${id}` : ""));
    if (!resp.ok) { box.replaceChildren(); return; }
    box.replaceChildren(renderSynthese(await resp.json(), box));
  } catch { box.replaceChildren(); }
}

function renderSynthese(syn, box) {
  const c = syn.contenu || {};
  const d = parseDate(syn.created_at);
  const when = d ? `${dayLabel(d)}, ${d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}` : "";
  const details = h("div", { class: "synth-details", hidden: true });
  const toggle = () => {
    details.hidden = !details.hidden;
    if (!details.hidden && !details.children.length) details.append(...renderSyntheseDetails(syn));
  };
  const rien = !c.action || /^rien\.?$/i.test(c.action.trim());
  return h("section", { class: "synth" },
    h("div", { class: "synth-kicker" }, when),
    h("p", { class: "synth-phrase", onclick: toggle }, syn.phrase),
    rien ? null : h("p", { class: "synth-action" }, "→ " + c.action),
    h("div", { class: "card-actions" },
      h("button", { class: "ibtn", "aria-label": "Détail", onclick: toggle }, "📝"),
      h("button", { class: "ibtn", "aria-label": "Écouter", onclick: () => listenSynthese(syn) }, "▶"),
      h("button", { class: "ibtn", "aria-label": "Une remarque", onclick: () => remarkSynthese(syn) }, "✎"),
      h("span", { class: "spacer" }),
      h("button", { class: "ibtn", "aria-label": "Synthèse précédente", disabled: !syn.prev_id,
        onclick: () => loadSynthese(box, syn.prev_id) }, "‹"),
      h("button", { class: "ibtn", "aria-label": "Synthèse suivante", disabled: !syn.next_id,
        onclick: () => loadSynthese(box, syn.next_id) }, "›"),
    ),
    details,
  );
}

function renderSyntheseDetails(syn) {
  const c = syn.contenu || {};
  const section = (title, items, fn) => items?.length ? h("section", {}, h("h3", {}, title), h("ul", { class: "synth-list" }, items.map(fn))) : null;
  const link = (url, label) => url ? h("a", { href: url, target: "_blank", rel: "noopener" }, label) : label;
  return [
    section("Confirmé", c.confirme, (p) => h("li", {}, p.point, " ", h("span", { class: "note" }, link(p.lien, p.source || "source"), " ↗"))),
    section("Faux ou non confirmé", c.faux_ou_non_confirme, (p) => h("li", {}, p.point, h("span", { class: "note" }, " — ", link(p.lien, p.raison || "")))),
    section("Ce qui a changé", c.delta, (t) => h("li", {}, t)),
    section("Ce qui ne se passe pas", c.ne_se_passe_pas, (t) => h("li", {}, t)),
    section("À creuser", c.a_creuser, (a) => h("li", {}, link(a.lien, a.titre), a.pourquoi ? h("span", { class: "note" }, " — " + a.pourquoi) : null)),
    c.questions_negatives?.length ? h("details", { class: "synth-more" }, h("summary", {}, "Questions négatives"),
      h("ul", { class: "synth-list" }, c.questions_negatives.map((q) => h("li", {}, h("b", {}, q.question), " ", q.reponse)))) : null,
    syn.corrections?.length ? h("details", { class: "synth-more" }, h("summary", {}, `Contradicteur (${syn.corrections.length})`),
      c.brouillon_phrase ? h("p", { class: "note" }, "Avant : « " + c.brouillon_phrase + " »") : null,
      h("ul", { class: "synth-list" }, syn.corrections.map((k) => h("li", {}, h("b", {}, k.type), " ", k.detail, k.raison ? h("span", { class: "note" }, " — " + k.raison) : null)))) : null,
  ].filter(Boolean);
}

function listenSynthese(syn) {
  const c = syn.contenu || {};
  const parts = [syn.phrase];
  if (c.action && !/^rien\.?$/i.test(c.action.trim())) parts.push("À faire : " + c.action);
  (c.confirme || []).forEach((p) => parts.push(p.point));
  if (c.delta?.length) parts.push("Ce qui a changé. " + c.delta.join(" "));
  if (c.faux_ou_non_confirme?.length) parts.push("Ce qui ne tient pas. " + c.faux_ou_non_confirme.map((p) => p.point).join(" "));
  playQueue(parts.map((p, i) => ({
    kicker: `${i + 1}/${parts.length}`, label: p,
    load: () => postJson("/api/tts", { text: p }).then((r) => r.blob()),
  })), "synthese");
}

async function remarkSynthese(syn) {
  const texte = window.prompt("Une remarque pour Xena (raté, faux, à revoir) :");
  if (!texte?.trim()) return;
  try { await postJson("/api/gap", { texte, synthese_id: syn.id }); } catch (e) { alert("⚠ " + e.message); }
}

async function loadMore(list, more) {
  more.disabled = true;
  try {
    const data = await (await api(`/api/articles?filtre=${filtre}&limit=40&offset=${feedState.offset}`)).json();
    feedState.offset += data.articles.length;
    for (const a of data.articles) {
      if (a.seen) seenIds.add(a.id);
      // Un dossier de plusieurs articles n'apparaît qu'une fois, au jour de sa dernière évolution
      const dossier = a.dossier?.n > 1 ? a.dossier : null;
      if (dossier && feedState.dossiers.has(dossier.id)) continue;
      const d = parseDate(a.ingested_at);
      const day = d ? dayLabel(d) : "";
      if (day !== feedState.lastDay) {
        list.append(h("div", { class: "day" }, day));
        feedState.lastDay = day;
      }
      if (dossier) feedState.dossiers.add(dossier.id);
      list.append(dossier ? renderDossierCard(a) : renderCard(a));
    }
    more.hidden = data.articles.length < 40;
  } catch (e) {
    list.append(h("p", { class: "empty" }, "Erreur : " + e.message));
  } finally {
    more.disabled = false;
  }
}

// Importance d'un coup d'œil : rouge > orange > jaune > blanc
function importance(score) {
  if (score >= 8.5) return { cls: "imp-red", label: "Majeure" };
  if (score >= 7.5) return { cls: "imp-orange", label: "Importante" };
  if (score >= 6.5) return { cls: "imp-yellow", label: "Notable" };
  return { cls: "imp-white", label: "Secondaire" };
}

// Confiance d'un coup d'œil : rien quand c'est confirmé, « ? » quand c'est allégué, « ✗ » quand c'est démenti
function statutMark(statut) {
  if (statut === "allegue") return h("span", { class: "st st-allegue", title: "Allégué" }, "?");
  if (statut === "dementi") return h("span", { class: "st st-dementi", title: "Démenti" }, "✗");
  return null;
}

// Grande image en tête de carte, comme un tweet. Wikipédia : un logo (png, svg) est montré en entier,
// un portrait est cadré sur le haut (le visage).
function media(url, onclick) {
  if (!url) return null;
  const wiki = /wikimedia\.org|wikipedia\.org/.test(url);
  const logo = wiki && /\.(svg|png)(\?|$)/i.test(url);
  return h("div", { class: "media" + (logo ? " contain" : wiki ? " portrait" : ""), onclick },
    h("img", { src: url, alt: "", loading: "lazy", referrerpolicy: "no-referrer",
      onerror: (e) => {
        const box = e.target.parentElement;
        box.closest(".card")?.classList.remove("has-media");
        box.remove();
      } }));
}

function renderCard(a) {
  const details = h("div", { class: "details", hidden: true });
  const imp = importance(a.score ?? 0);
  const open = () => toggleDetails(a, details);
  return h("article", { class: "card" + (a.seen ? " seen" : "") + (a.image ? " has-media" : ""), "data-card": a.id },
    media(a.image, open),
    h("div", { class: "card-main", onclick: (e) => { if (!e.target.closest("button")) open(); } },
      h("h2", {}, h("span", { class: `imp ${imp.cls}`, title: imp.label }), statutMark(a.statut), a.titre),
    ),
    h("div", { class: "card-actions" },
      h("button", { class: "ibtn", "aria-label": "Lire la fiche", onclick: () => toggleDetails(a, details) }, "📝"),
      h("button", { class: "ibtn", "aria-label": "Écouter", onclick: () => listenArticle(a) }, "▶"),
      h("button", { class: "ibtn", "aria-label": "En parler", onclick: () => openChat(a) }, "🎙"),
    ),
    details,
  );
}

// ------------------------------------------------------------------ dossiers vivants
// Une histoire qui évolue = une carte : son nom, puis où en est la situation, en une phrase.
// Le fil se déplie : une étape par changement d'état, les nouvelles depuis la dernière lecture en avant.
function renderDossierCard(a) {
  const d = a.dossier;
  const details = h("div", { class: "details", hidden: true });
  const imp = importance(a.score ?? 0);
  const open = () => toggleDossier(d, details);
  const image = d.image || a.image;
  return h("article", { class: "card dossier" + (d.unseen ? "" : " seen") + (image ? " has-media" : ""), "data-dossier": d.id },
    media(image, open),
    h("div", { class: "card-main", onclick: (e) => { if (!e.target.closest("button")) open(); } },
      h("div", { class: "card-text" },
        h("h2", {}, h("span", { class: `imp ${imp.cls}`, title: imp.label }), d.titre),
        h("p", { class: "etat" }, statutMark(d.statut), d.etat),
      ),
    ),
    h("div", { class: "card-actions" },
      h("button", { class: "ibtn", "aria-label": "Suivre le fil", onclick: open }, "🧵",
        d.unseen ? h("span", { class: "badge new" }, d.unseen) : null),
      h("button", { class: "ibtn", "aria-label": "Écouter", onclick: () => listenArticle(a) }, "▶"),
      h("button", { class: "ibtn", "aria-label": "En parler", onclick: () => openChat(a) }, "🎙"),
    ),
    details,
  );
}

function shortDate(s) {
  const d = parseDate(s);
  if (!d) return "";
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) + " " +
    d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

async function toggleDossier(d, details) {
  if (!details.hidden) { details.hidden = true; return; }
  details.hidden = false;
  if (details.dataset.loaded) return;
  details.replaceChildren(h("p", { class: "note" }, "…"));
  try {
    const data = await (await api(`/api/dossiers/${d.id}`)).json();
    details.replaceChildren(...data.events.map((e) => {
      const isNew = e.articles.some((x) => !x.seen && !seenIds.has(x.id));
      const sub = h("div", { class: "step-articles", hidden: true }, e.articles.map(renderCard));
      return h("div", { class: "step" + (isNew ? " new" : "") },
        h("div", { class: "step-head", onclick: () => { sub.hidden = !sub.hidden; } },
          h("span", { class: "step-date" }, shortDate(e.created_at)),
          h("span", { class: "step-phrase" }, statutMark(e.statut), e.phrase),
          e.articles.length > 1 ? h("span", { class: "step-n", title: "Sources" }, `×${e.articles.length}`) : null,
        ),
        sub,
      );
    }));
    details.dataset.loaded = "1";
    // Le fil a été lu : la prochaine fois, seules les nouvelles étapes ressortent
    data.events.forEach((e) => e.articles.forEach((x) => markSeen(x.id)));
    document.querySelectorAll(`[data-dossier="${d.id}"]`).forEach((c) => {
      c.classList.add("seen");
      c.querySelector(".badge.new")?.remove();
    });
  } catch (e) {
    details.replaceChildren(h("p", { class: "note" }, "Erreur : " + e.message));
  }
}

async function toggleDetails(a, details) {
  if (!details.hidden) {
    details.hidden = true;
    return;
  }
  details.hidden = false;
  markSeen(a.id);
  if (details.dataset.loaded) return;
  details.replaceChildren(h("p", { class: "note" }, "…"));
  try {
    const full = await (await api(`/api/articles/${a.id}`)).json();
    Object.assign(a, { brief: full.brief, url: full.url });
    details.replaceChildren(...renderBrief(a, full).filter(Boolean));
    details.dataset.loaded = "1";
  } catch (e) {
    details.replaceChildren(h("p", { class: "note" }, "Erreur : " + e.message));
  }
}

function renderBrief(a, full) {
  const b = full.brief || {};
  const section = (title, ...content) => h("section", {}, h("h3", {}, title), ...content);
  return [
    full.confiance ? h("p", { class: "confiance" }, statutMark(full.statut), full.confiance) : null,
    h("p", { class: "lead" }, b.chapo || a.chapo),
    h("div", { class: "prose" }, (b.recit?.length ? b.recit : [full.factual_core || ""]).map((p) => h("p", {}, p))),
    b.pourquoi_ca_compte ? section("Pourquoi ça compte", h("div", { class: "prose" }, h("p", {}, b.pourquoi_ca_compte))) : null,
    section("Version de la partie mise en cause",
      h("div", { class: "prose" }, h("p", {}, b.version_mise_en_cause || full.counter_view || "Non mentionnée."))),
    b.concepts?.length ? section("Pour bien comprendre", h("div", { class: "box" }, b.concepts.map((c) =>
      h("div", { class: "concept" },
        h("b", {}, c.terme),
        h("p", {}, c.explication),
        h("button", { class: "ibtn", "aria-label": "En parler", onclick: () => openChat(a, `Explique-moi plus en détail « ${c.terme} », et son rôle exact dans cette affaire.`) }, "🎙"),
      )))) : null,
    b.questions_ouvertes?.length ? section("Ce qu'on ne sait pas encore",
      h("div", { class: "prose" }, b.questions_ouvertes.map((q) => h("p", {}, q)))) : null,
    section("Source",
      b.angle_source || full.framing ? h("p", { class: "note" }, "Angle : " + (b.angle_source || full.framing)) : null,
      full.source_quote ? h("p", { class: "quote" }, full.source_quote) : null,
      b.limites ? h("p", { class: "note" }, b.limites) : null,
      h("a", { class: "source-link", href: full.url, target: "_blank", rel: "noopener" }, `${full.source} ↗`),
    ),
  ];
}

// ------------------------------------------------------------------ discussion
// Une seule conversation, qui connaît toutes les news de la semaine ; on peut la centrer sur un article.
// L'historique vit en base côté serveur ; le navigateur ne garde que l'identifiant de la conversation en cours.
const newConversationId = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
const chat = { id: store.get("xena-conv", null) || newConversationId(), focus: null, history: [], loaded: false, lastAnswer: "" };
store.set("xena-conv", chat.id);

async function loadConversation() {
  if (chat.loaded) return;
  try {
    const data = await (await api(`/api/conversations/${chat.id}`)).json();
    chat.history = data.messages;
    chat.loaded = true;
    const last = [...chat.history].reverse().find((t) => t.role === "model");
    if (last) chat.lastAnswer = last.text;
  } catch { /* hors ligne : on repart d'une conversation vide à l'écran */ }
}

function setFocus(article) {
  chat.focus = article || null;
  $("#focus").hidden = !article;
  $("#focus-title").textContent = article ? article.titre : "";
}

async function openChat(article, initialQuestion) {
  unlockAudio();
  if (article) { setFocus(article); markSeen(article.id); }
  $("#chat").hidden = false;
  await loadConversation();
  renderChatLog();
  if (initialQuestion) sendQuestion(initialQuestion);
}

function closeChat() {
  if (queue.kind === "chat") stopAll();
  if (recorder.active) { clearInterval(recorder.timer); recorder.cancel(); }
  $("#chat").hidden = true;
}

function paragraphs(text) {
  return text.split(/\n\s*\n/).map((p) => p.replace(/\s+/g, " ").trim()).filter(Boolean);
}

function renderChatLog() {
  const log = $("#chat-log");
  log.replaceChildren();
  for (const turn of chat.history) log.append(renderMsg(turn));
  log.scrollTop = log.scrollHeight;
}

function renderMsg(turn) {
  if (turn.role === "user") {
    return h("div", { class: "msg user" }, h("div", { class: "body" }, turn.text));
  }
  const searched = turn.queries?.length;
  return h("div", { class: "msg model" },
    h("div", { class: "body" }, paragraphs(turn.text).map((p) => h("p", {}, p))),
    searched
      ? h("details", { class: "grounding" },
          h("summary", {}, `🔎 ${turn.sources?.length || turn.queries.length}`),
          h("div", {}, turn.queries.join(" · ")),
          h("div", { class: "sources" }, (turn.sources || []).map((s) =>
            h("a", { href: s.url, target: "_blank", rel: "noopener" }, s.title))))
      : h("div", { class: "grounding warn", title: "Réponse sans recherche web" }, "⚠ sans recherche"));
}

function setStatus(text) { $("#chat-status").textContent = text || ""; }

async function sendQuestion(text, pending) {
  if (queue.kind === "chat") stopAll();
  if (!pending) {
    pending = { role: "user", text };
    chat.history.push(pending);
    renderChatLog();
  }
  const t0 = Date.now();
  setStatus("…");
  const timer = setInterval(() => setStatus(`… ${Math.round((Date.now() - t0) / 1000)} s`), 1000);
  $("#mic").disabled = true;
  try {
    const resp = await postJson("/api/chat", { conversation_id: chat.id, article_id: chat.focus?.id || "", text });
    const { answer, queries, sources } = await resp.json();
    chat.history.push({ role: "model", text: answer, queries, sources });
    renderChatLog();
    setStatus("");
    speak(answer);
  } catch (e) {
    setStatus("⚠ " + e.message);
  } finally {
    clearInterval(timer);
    $("#mic").disabled = false;
  }
}

// --- voix des réponses : paragraphe par paragraphe, le suivant se prépare pendant la lecture
function highlight(index) {
  document.querySelectorAll("p.speaking").forEach((p) => p.classList.remove("speaking"));
  if (index < 0) return;
  const msgs = document.querySelectorAll("#chat-log .msg.model");
  const p = msgs[msgs.length - 1]?.querySelectorAll(".body p")[index];
  if (p) { p.classList.add("speaking"); p.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
}

function speak(text) {
  chat.lastAnswer = text;
  const parts = paragraphs(text);
  if (!parts.length) return;
  if (settings.voice === "browser") { stopAll(); return speakBrowser(parts); }
  playQueue(parts.map((p, i) => ({
    label: "",
    load: () => postJson("/api/tts", { text: p }).then((r) => r.blob()),
    onStart: () => highlight(i),
  })), "chat");
}

function pickFrenchVoice() {
  const voices = speechSynthesis.getVoices().filter((v) => v.lang?.toLowerCase().startsWith("fr"));
  return voices.find((v) => /premium|enhanced|amélioré/i.test(v.name)) ||
    voices.find((v) => /thomas|amélie|audrey|aurélie/i.test(v.name)) ||
    voices.find((v) => v.lang === "fr-FR") || voices[0];
}

function speakBrowser(parts) {
  if (!window.speechSynthesis) return;
  const voice = pickFrenchVoice();
  parts.forEach((text, i) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "fr-FR";
    if (voice) u.voice = voice;
    u.rate = settings.speed;
    u.onstart = () => highlight(i);
    speechSynthesis.speak(u);
  });
}

// --- micro : enregistrement libre (pas de coupure automatique)
// MediaRecorder donne le format natif du navigateur (mp4/AAC sur Safari, webm/Opus sur Chrome), que Gemini lit directement.
// Repli en WAV via Web Audio pour les navigateurs sans MediaRecorder.
const recorder = {
  active: false, stream: null, media: null, chunks: [], mime: "", startedAt: 0, timer: null, ctx: null, node: null,

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
    this.chunks = [];
    this.peak = 0;
    this._meter();
    if (window.MediaRecorder) {
      const type = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"].find((t) => MediaRecorder.isTypeSupported?.(t));
      this.media = new MediaRecorder(this.stream, type ? { mimeType: type } : undefined);
      this.mime = this.media.mimeType || type || "audio/mp4";
      this.media.ondataavailable = (e) => { if (e.data?.size) this.chunks.push(e.data); };
      this.media.start(1000);
    } else {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new Ctx();
      await this.ctx.resume();
      const source = this.ctx.createMediaStreamSource(this.stream);
      this.node = this.ctx.createScriptProcessor(4096, 1, 1);
      const mute = this.ctx.createGain();
      mute.gain.value = 0;
      this.node.onaudioprocess = (e) => this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      source.connect(this.node);
      this.node.connect(mute);
      mute.connect(this.ctx.destination);
      this.mime = "audio/wav";
    }
    this.active = true;
    this.startedAt = Date.now();
  },

  _meter() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.meterCtx = new Ctx();
      this.meterCtx.resume();
      const analyser = this.meterCtx.createAnalyser();
      analyser.fftSize = 1024;
      this.meterCtx.createMediaStreamSource(this.stream).connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      this.meterTimer = setInterval(() => {
        analyser.getFloatTimeDomainData(buf);
        for (const x of buf) this.peak = Math.max(this.peak, Math.abs(x));
      }, 100);
    } catch { this.peak = -1; } // mesure impossible : on n'en tient pas compte
  },

  _release() {
    clearInterval(this.meterTimer);
    this.meterCtx?.close();
    this.meterCtx = null;
    this.active = false;
    if (this.node) this.node.onaudioprocess = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
    this.ctx = this.node = null;
  },

  cancel() {
    if (this.media && this.media.state !== "inactive") this.media.stop();
    this.media = null;
    this._release();
    this.chunks = [];
    updateMic();
  },

  // -> Promise<{ blob, mime }>
  stop() {
    if (this.media) {
      const media = this.media;
      this.media = null;
      return new Promise((resolve) => {
        media.onstop = () => {
          this._release();
          resolve({ blob: new Blob(this.chunks, { type: this.mime }), mime: this.mime });
        };
        media.stop();
      });
    }
    const rate = this.ctx.sampleRate;
    const wav = encodeWav(this.chunks, rate, 16000);
    this._release();
    return Promise.resolve({ blob: new Blob([wav], { type: "audio/wav" }), mime: "audio/wav" });
  },
};

function encodeWav(chunks, inRate, outRate) {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const input = new Float32Array(total);
  let pos = 0;
  for (const c of chunks) { input.set(c, pos); pos += c.length; }
  const ratio = inRate / outRate;
  const outLen = Math.floor(total / ratio);
  const buf = new ArrayBuffer(44 + outLen * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + outLen * 2, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, outRate, true); v.setUint32(28, outRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, outLen * 2, true);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio), end = Math.min(Math.floor((i + 1) * ratio), total);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    const s = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buf);
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function updateMic() {
  $("#mic").classList.toggle("recording", recorder.active);
  if (recorder.active) {
    const s = Math.round((Date.now() - recorder.startedAt) / 1000);
    $("#mic-label").textContent = `● ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  } else {
    $("#mic-label").textContent = "🎙";
  }
}

async function onMic() {
  unlockAudio();
  if (!recorder.active) {
    if (queue.kind === "chat") stopAll(); else player.pause();
    if (window.speechSynthesis) speechSynthesis.cancel();
    try {
      await recorder.start();
    } catch (e) {
      setStatus("Micro inaccessible : " + e.message);
      return;
    }
    setStatus("");
    recorder.timer = setInterval(() => {
      updateMic();
      if (Date.now() - recorder.startedAt > 10 * 60 * 1000) onMic(); // limite de sécurité : 10 min
    }, 500);
    updateMic();
  } else {
    clearInterval(recorder.timer);
    const seconds = (Date.now() - recorder.startedAt) / 1000;
    const { blob, mime } = await recorder.stop();
    updateMic();
    if (seconds < 0.8) return;
    if (!blob.size || recorder.peak === 0) { setStatus("⚠ micro muet"); return; }
    // 1) transcription rapide : la question s'affiche tout de suite
    const pending = { role: "user", text: "🎙 …" };
    chat.history.push(pending);
    renderChatLog();
    $("#mic").disabled = true;
    setStatus("…");
    let text = "";
    try {
      const resp = await postJson("/api/transcribe", { audio_b64: await blobToBase64(blob), mime });
      text = (await resp.json()).text;
    } catch (e) {
      chat.history.pop();
      renderChatLog();
      setStatus("⚠ " + e.message);
      $("#mic").disabled = false;
      return;
    }
    if (!text) {
      chat.history.pop();
      renderChatLog();
      setStatus("🎙 rien entendu");
      $("#mic").disabled = false;
      return;
    }
    pending.text = text;
    renderChatLog();
    // 2) réponse
    sendQuestion(text, pending);
  }
}

function geminiPrompt() {
  const lines = [
    "Je veux discuter avec toi de l'actualité, à l'oral. Sois précis et exigeant, vérifie sur le web avant d'affirmer, et parle lentement.",
  ];
  const a = chat.focus;
  if (a) {
    const b = a.brief || {};
    lines.push("", `Article : ${b.titre || a.titre}`, `Source : ${a.source} — ${a.url}`, "",
      b.chapo || a.chapo || "", ...(b.recit || []),
      `Version de la partie mise en cause : ${b.version_mise_en_cause || "non mentionnée"}`);
  }
  return lines.join("\n");
}

function initChat() {
  $("#talk-fab").addEventListener("click", () => openChat(null));
  $("#mic").addEventListener("click", onMic);
  $("#chat-close").addEventListener("click", closeChat);
  $("#focus-clear").addEventListener("click", () => setFocus(null));
  $("#chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#chat-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    unlockAudio();
    sendQuestion(text);
  });
  $("#stop-voice").addEventListener("click", () => { if (queue.kind === "chat") stopAll(); window.speechSynthesis?.cancel(); });
  $("#replay").addEventListener("click", () => { unlockAudio(); if (chat.lastAnswer) speak(chat.lastAnswer); });
  $("#clear-chat").addEventListener("click", () => {
    if (queue.kind === "chat") stopAll();
    chat.id = newConversationId();
    store.set("xena-conv", chat.id);
    chat.history = [];
    chat.loaded = true;
    setFocus(null);
    renderChatLog();
  });
  $("#to-gemini").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(geminiPrompt());
      setStatus("Contexte copié");
    } catch {
      setStatus("");
    }
    window.open("https://gemini.google.com/app", "_blank", "noopener");
  });
}

// ------------------------------------------------------------------ démarrage
initSettings();
initTabs();
initChat();
$("#flash-btn").addEventListener("click", playFlash);
if (window.speechSynthesis) speechSynthesis.getVoices();
$("#push-toggle").addEventListener("click", togglePush);
$("#push-test").addEventListener("click", testPush);
initServiceWorker();
renderFeed().then(openFromHash);
window.addEventListener("hashchange", openFromHash);
refreshFlashCount();
setInterval(refreshFlashCount, 5 * 60 * 1000);
