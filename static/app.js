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

const timeLabel = (d) => d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function scoreBadge(score, seuil) {
  return h("span", { class: "score" + (score >= seuil ? "" : " low") }, (score ?? 0).toFixed(1));
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
  $("#settings-btn").addEventListener("click", () => { $("#settings").hidden = !$("#settings").hidden; });
}

// ------------------------------------------------------------------ audio
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

let currentObjectUrl = null;
function playBlob(blob, label, showBar) {
  if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
  currentObjectUrl = URL.createObjectURL(blob);
  player.src = currentObjectUrl;
  $("#player-label").textContent = label || "";
  $("#player-bar").hidden = !showBar;
  applyRate();
  return player.play();
}

$("#player-close").addEventListener("click", () => { player.pause(); $("#player-bar").hidden = true; });
player.addEventListener("loadedmetadata", applyRate);

async function playSummary(article, btn) {
  unlockAudio();
  stopSpeaking();
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "Préparation de l'audio…";
  try {
    const blob = await (await api(`/api/articles/${article.id}/audio`)).blob();
    await playBlob(blob, article.titre, true);
  } catch (e) {
    alert("Audio indisponible : " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

// ------------------------------------------------------------------ liste
let filtre = store.get("xena-filtre", "top");
let listState = { offset: 0, done: false, lastDay: null };

function initTabs() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.filtre === filtre);
    t.addEventListener("click", () => {
      filtre = t.dataset.filtre;
      store.set("xena-filtre", filtre);
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
      if (location.hash && location.hash !== "#/") location.hash = "#/"; else renderList();
    });
  });
}

async function renderList() {
  $("#tabs").hidden = false;
  const app = $("#app");
  app.replaceChildren(h("div", { class: "loading" }, "Chargement…"));
  listState = { offset: 0, done: false, lastDay: null };
  const container = h("div", {});
  const more = h("button", { class: "btn ghost more", onclick: () => loadMore(container, more) }, "Plus de news");
  await loadMore(container, more);
  app.replaceChildren(container, more);
  if (!container.children.length) app.replaceChildren(h("p", { class: "empty" }, "Rien pour l'instant."));
}

async function loadMore(container, more) {
  more.disabled = true;
  try {
    const data = await (await api(`/api/articles?filtre=${filtre}&limit=40&offset=${listState.offset}`)).json();
    listState.offset += data.articles.length;
    for (const a of data.articles) {
      const d = parseDate(a.ingested_at);
      const day = d ? dayLabel(d) : "";
      if (day !== listState.lastDay) {
        container.append(h("div", { class: "day" }, day));
        listState.lastDay = day;
      }
      container.append(h("a", { class: "card", href: `#/a/${a.id}` },
        h("div", { class: "meta" }, scoreBadge(a.score, data.seuil), h("span", {}, a.source), d ? h("span", {}, "· " + timeLabel(d)) : null),
        h("h2", {}, a.titre),
        a.chapo ? h("p", {}, a.chapo) : null,
      ));
    }
    more.hidden = data.articles.length < 40;
  } catch (e) {
    container.append(h("p", { class: "empty" }, "Erreur : " + e.message));
  } finally {
    more.disabled = false;
  }
}

// ------------------------------------------------------------------ article
let currentArticle = null;

async function renderArticle(id) {
  $("#tabs").hidden = true;
  const app = $("#app");
  app.replaceChildren(
    h("a", { class: "back", href: "#/" }, "← Retour"),
    h("div", { class: "loading" }, "Lecture de l'article et préparation de la fiche… (quelques secondes la première fois)"),
  );
  let a;
  try {
    a = await (await api(`/api/articles/${id}`)).json();
  } catch (e) {
    app.append(h("p", { class: "empty" }, "Erreur : " + e.message));
    return;
  }
  currentArticle = a;
  const b = a.brief || {};
  const d = parseDate(a.published_at) || parseDate(a.ingested_at);

  const listenBtn = h("button", { class: "btn", onclick: () => playSummary(a, listenBtn) }, "▶ Écouter le résumé");
  const talkBtn = h("button", { class: "btn ghost", onclick: () => openChat(a) }, "🎙 En discuter");

  const section = (title, ...content) => h("section", {}, h("h3", {}, title), ...content);

  app.replaceChildren(h("article", { class: "article" },
    h("a", { class: "back", href: "#/" }, "← Retour"),
    h("div", { class: "meta" }, scoreBadge(a.score, 0), h("span", {}, a.source),
      d ? h("span", {}, "· " + d.toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short" })) : null),
    h("h1", {}, b.titre || a.titre),
    h("p", { class: "chapo" }, b.chapo || a.chapo),
    h("div", { class: "actions" }, listenBtn, talkBtn),

    b.recit?.length ? h("div", { class: "prose" }, b.recit.map((p) => h("p", {}, p))) :
      h("div", { class: "prose" }, h("p", {}, a.factual_core || "")),

    b.pourquoi_ca_compte ? section("Pourquoi ça compte", h("div", { class: "prose" }, h("p", {}, b.pourquoi_ca_compte))) : null,

    section("Version de la partie mise en cause",
      h("div", { class: "prose" }, h("p", {}, b.version_mise_en_cause || a.counter_view || "Non mentionnée."))),

    b.concepts?.length ? section("Pour bien comprendre", h("div", { class: "box" }, b.concepts.map((c) =>
      h("div", { class: "concept" },
        h("b", {}, c.terme),
        h("p", {}, c.explication),
        h("button", { class: "link-btn", onclick: () => openChat(a, `Explique-moi plus en détail « ${c.terme} », et son rôle exact dans cette affaire.`) }, "Creuser à l'oral →"),
      )))) : null,

    b.questions_ouvertes?.length ? section("Ce qu'on ne sait pas encore",
      h("div", { class: "prose" }, b.questions_ouvertes.map((q) => h("p", {}, q)))) : null,

    section("Source",
      b.angle_source || a.framing ? h("p", { class: "note" }, "Angle : " + (b.angle_source || a.framing)) : null,
      a.source_quote ? h("p", { class: "quote" }, a.source_quote) : null,
      b.limites ? h("p", { class: "note" }, b.limites) : null,
      h("p", { class: "note" }, "Titre d'origine : " + a.title_original),
      h("a", { class: "source-link", href: a.url, target: "_blank", rel: "noopener" }, `Lire sur ${a.source} ↗`),
    ),
  ));
  window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ discussion
const chat = { article: null, history: [], speakToken: 0, lastAnswer: "" };

function chatKey(id) { return `xena-chat-${id}`; }

function openChat(article, initialQuestion) {
  unlockAudio();
  if (chat.article?.id !== article.id) {
    chat.article = article;
    chat.history = store.get(chatKey(article.id), []);
    $("#chat-sub").textContent = (article.brief?.titre || article.titre);
    renderChatLog();
  }
  $("#chat").hidden = false;
  if (initialQuestion) sendQuestion({ text: initialQuestion });
}

function closeChat() {
  stopSpeaking();
  if (recorder.active) recorder.cancel();
  $("#chat").hidden = true;
}

function paragraphs(text) {
  return text.split(/\n\s*\n/).map((p) => p.replace(/\s+/g, " ").trim()).filter(Boolean);
}

function renderChatLog() {
  const log = $("#chat-log");
  log.replaceChildren();
  if (!chat.history.length) {
    log.append(h("p", { class: "note" },
      "Pose ta question à voix haute : appuie une fois pour parler, prends tout ton temps, puis appuie à nouveau pour envoyer."));
  }
  for (const turn of chat.history) log.append(renderMsg(turn));
  log.scrollTop = log.scrollHeight;
}

function renderMsg(turn) {
  if (turn.role === "user") {
    return h("div", { class: "msg user" }, h("div", { class: "who" }, "Toi"), h("div", { class: "body" }, turn.text));
  }
  return h("div", { class: "msg model" }, h("div", { class: "who" }, "Xena"),
    h("div", { class: "body" }, paragraphs(turn.text).map((p) => h("p", {}, p))));
}

function setStatus(text) { $("#chat-status").textContent = text || ""; }

async function sendQuestion({ text, audioB64 }) {
  stopSpeaking();
  const article = chat.article;
  const pending = { role: "user", text: text || "🎙 …" };
  chat.history.push(pending);
  renderChatLog();
  const t0 = Date.now();
  setStatus("Xena réfléchit…");
  const timer = setInterval(() => setStatus(`Xena réfléchit… ${Math.round((Date.now() - t0) / 1000)} s`), 1000);
  $("#mic").disabled = true;
  try {
    const history = chat.history.slice(0, -1);
    const resp = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article_id: article.id, history, text, audio_b64: audioB64 }),
    });
    const { question, answer } = await resp.json();
    if (chat.article !== article) return;
    pending.text = question || pending.text;
    chat.history.push({ role: "model", text: answer });
    store.set(chatKey(article.id), chat.history);
    renderChatLog();
    setStatus("");
    speak(answer);
  } catch (e) {
    chat.history.pop();
    renderChatLog();
    setStatus("Erreur : " + e.message);
  } finally {
    clearInterval(timer);
    $("#mic").disabled = false;
  }
}

// --- voix des réponses : paragraphe par paragraphe, le suivant se prépare pendant la lecture
function stopSpeaking() {
  chat.speakToken++;
  if (window.speechSynthesis) speechSynthesis.cancel();
  if (!$("#player-bar").hidden) return; // ne coupe pas le résumé audio en cours
  player.pause();
  document.querySelectorAll("p.speaking").forEach((p) => p.classList.remove("speaking"));
}

function highlight(index) {
  const msgs = document.querySelectorAll("#chat-log .msg.model");
  const last = msgs[msgs.length - 1];
  document.querySelectorAll("p.speaking").forEach((p) => p.classList.remove("speaking"));
  const p = last?.querySelectorAll(".body p")[index];
  if (p) { p.classList.add("speaking"); p.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
}

function playUntilEnd(blob) {
  return new Promise((resolve) => {
    const done = () => { player.removeEventListener("ended", done); player.removeEventListener("pause", done); resolve(); };
    player.addEventListener("ended", done);
    player.addEventListener("pause", done);
    playBlob(blob, "", false).catch(done);
  });
}

async function speak(text) {
  chat.lastAnswer = text;
  const token = ++chat.speakToken;
  const parts = paragraphs(text);
  if (!parts.length) return;
  if (!$("#player-bar").hidden) { player.pause(); $("#player-bar").hidden = true; }

  if (settings.voice === "browser" || !window.fetch) return speakBrowser(parts, token);

  const tts = (t) => api("/api/tts", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: t }),
  }).then((r) => r.blob());

  let next = tts(parts[0]);
  for (let i = 0; i < parts.length; i++) {
    let blob;
    try { blob = await next; } catch (e) {
      if (token === chat.speakToken) setStatus("Voix Gemini indisponible, voix du navigateur.");
      return speakBrowser(parts.slice(i), token, i);
    }
    if (token !== chat.speakToken) return;
    if (i + 1 < parts.length) next = tts(parts[i + 1]);
    highlight(i);
    await playUntilEnd(blob);
    if (token !== chat.speakToken) return;
    await new Promise((r) => setTimeout(r, 350)); // respiration entre les paragraphes
  }
  highlight(-1);
}

function pickFrenchVoice() {
  const voices = speechSynthesis.getVoices().filter((v) => v.lang?.toLowerCase().startsWith("fr"));
  return voices.find((v) => /premium|enhanced|amélioré/i.test(v.name)) ||
    voices.find((v) => /thomas|amélie|audrey|aurélie/i.test(v.name)) ||
    voices.find((v) => v.lang === "fr-FR") || voices[0];
}

function speakBrowser(parts, token, offset = 0) {
  if (!window.speechSynthesis) return;
  const voice = pickFrenchVoice();
  parts.forEach((text, i) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "fr-FR";
    if (voice) u.voice = voice;
    u.rate = settings.speed;
    u.onstart = () => { if (token === chat.speakToken) highlight(i + offset); };
    speechSynthesis.speak(u);
  });
}

// --- micro : enregistrement libre (pas de coupure automatique), envoyé en WAV 16 kHz
const recorder = {
  active: false, stream: null, ctx: null, node: null, chunks: [], startedAt: 0, timer: null,

  async start() {
    // Le contexte audio est créé avant tout await, pendant le geste (exigence de Safari iOS)
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new Ctx();
    const resumed = this.ctx.resume();
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
    } catch (e) {
      this.ctx.close();
      throw e;
    }
    await resumed;
    const source = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    const mute = this.ctx.createGain();
    mute.gain.value = 0;
    this.chunks = [];
    this.node.onaudioprocess = (e) => this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    source.connect(this.node);
    this.node.connect(mute);
    mute.connect(this.ctx.destination);
    this.active = true;
    this.startedAt = Date.now();
  },

  _release() {
    this.active = false;
    this.node && (this.node.onaudioprocess = null);
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
  },

  cancel() { this._release(); this.chunks = []; updateMic(); },

  stop() {
    const rate = this.ctx.sampleRate;
    this._release();
    return encodeWav(this.chunks, rate, 16000);
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
    // moyenne sur la fenêtre (anti-repliement simple)
    const start = Math.floor(i * ratio), end = Math.min(Math.floor((i + 1) * ratio), total);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    const s = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buf);
}

function toBase64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

function updateMic() {
  const mic = $("#mic");
  mic.classList.toggle("recording", recorder.active);
  if (recorder.active) {
    const s = Math.round((Date.now() - recorder.startedAt) / 1000);
    $("#mic-label").textContent = `Je t'écoute… ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} · appuie pour envoyer`;
  } else {
    $("#mic-label").textContent = "Appuie pour parler";
  }
}

async function onMic() {
  unlockAudio();
  if (!recorder.active) {
    stopSpeaking();
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
    const wav = recorder.stop();
    updateMic();
    if (seconds < 0.8) { setStatus("Trop court, réessaie."); return; }
    sendQuestion({ audioB64: toBase64(wav) });
  }
}

function geminiPrompt(a) {
  const b = a.brief || {};
  return [
    "Je veux discuter avec toi de cette actualité, à l'oral. Sois précis et exigeant, ne simplifie pas jusqu'à devenir faux, et parle lentement.",
    "",
    `Titre : ${b.titre || a.titre}`,
    `Source : ${a.source} — ${a.url}`,
    "",
    b.chapo || a.chapo || "",
    ...(b.recit || []),
    b.pourquoi_ca_compte ? `Pourquoi ça compte : ${b.pourquoi_ca_compte}` : "",
    `Version de la partie mise en cause : ${b.version_mise_en_cause || a.counter_view || "non mentionnée"}`,
  ].join("\n");
}

function initChat() {
  $("#mic").addEventListener("click", onMic);
  $("#chat-close").addEventListener("click", closeChat);
  $("#chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#chat-input");
    const text = input.value.trim();
    if (!text || !chat.article) return;
    input.value = "";
    unlockAudio();
    sendQuestion({ text });
  });
  $("#stop-voice").addEventListener("click", () => { chat.speakToken++; window.speechSynthesis?.cancel(); player.pause(); });
  $("#replay").addEventListener("click", () => { unlockAudio(); if (chat.lastAnswer) speak(chat.lastAnswer); });
  $("#clear-chat").addEventListener("click", () => {
    if (!chat.article) return;
    stopSpeaking();
    chat.history = [];
    store.set(chatKey(chat.article.id), []);
    renderChatLog();
  });
  $("#to-gemini").addEventListener("click", async () => {
    if (!chat.article) return;
    try {
      await navigator.clipboard.writeText(geminiPrompt(chat.article));
      setStatus("Contexte copié : colle-le dans Gemini, puis lance Gemini Live.");
    } catch {
      setStatus("Copie impossible, ouvre Gemini et décris l'article.");
    }
    window.open("https://gemini.google.com/app", "_blank", "noopener");
  });
}

// ------------------------------------------------------------------ routage
function route() {
  const m = location.hash.match(/^#\/a\/([0-9a-f]{16})$/);
  if (m) {
    if (chat.article && chat.article.id !== m[1]) closeChat();
    renderArticle(m[1]);
  }
  else { closeChat(); renderList(); }
}

initSettings();
initTabs();
initChat();
if (window.speechSynthesis) speechSynthesis.getVoices();
window.addEventListener("hashchange", route);
route();
