"use strict";
/*
 * det-coach practice app. Plain JavaScript, no build step, no dependencies.
 *
 * Routes
 *   #/                       home: rounds and past attempts
 *   #/exam/<round>           take a round with the official timings
 *   #/exam/<round>/<section> take one section of a round (reading, listening, writing, speaking)
 *   #/attempt/<id>           answers, recordings, transcripts and feedback
 *   #/preview/<round>/<step>[/<stage>] one exam screen without timers (screenshots, round authors).
 *     Stages: missing, highlight, idea, title (Interactive Reading), respond (Interactive Listening)
 */

// ---------- small helpers ----------

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const wordCount = (text) => (text.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g) || []).length; // as metrics.WORD
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const clockText = (s) => {
  s = Math.max(0, Math.ceil(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const duration = (s) => {
  const m = Math.floor(s / 60), r = s % 60;
  if (s >= 60 && !r) return plural(m, "minute");
  if (s <= 90) return `${s} seconds`;
  return `${m} min ${r} s`;
};
const shortDuration = (s) => (s < 60 ? `${s} s` : s % 60 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : `${s / 60} min`);
const when = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${path} returned ${r.status}`);
    return r.json();
  },
  async post(path, body = {}, type = "application/json") {
    const data = type === "application/json" ? JSON.stringify(body) : body;
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": type }, body: data });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `${path} returned ${r.status}`);
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: "DELETE" });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `${path} returned ${r.status}`);
    return r.json();
  },
};

const ICON = {
  pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/></svg>',
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/></svg>',
  ear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 14v-2a9 9 0 0 1 18 0v2"/><rect x="2" y="14" width="5" height="7" rx="2"/><rect x="17" y="14" width="5" height="7" rx="2"/></svg>',
  speaker: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path fill="none" d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  cross: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.5.9l10.5-6.5a1 1 0 0 0 0-1.8L9.5 4.6A1 1 0 0 0 8 5.5Z"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4h7a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H2zM22 4h-7a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h8z"/></svg>',
};

const TASK_ICON = {
  read_select: "book", fill_blanks: "book", read_complete: "book", listen_type: "ear",
  interactive_reading: "book", interactive_listening: "ear",
  write_photo: "pen", interactive_writing: "pen", summarize_conversation: "ear", writing_sample: "pen",
  speak_photo: "mic", read_then_speak: "mic", interactive_speaking: "chat", speaking_sample: "mic",
};

// The titles follow the wording of the official test screens.
function screenTitle(step) {
  const time = duration(step.answer);
  switch (step.type) {
    case "read_select": return "Is this a real English word?";
    case "fill_blanks": return "Complete the sentence with the correct word";
    case "read_complete": return "Complete the text with the correct words";
    case "listen_type": return "Type what you hear";
    case "write_photo": return `Write a description of the image below for ${time}`;
    case "interactive_writing": return step.show_previous ? `Write a follow-up response for ${time}` : `Write about the topic below for ${time}`;
    case "summarize_conversation": return `Write a summary of the conversation ${step.after ? "you just had" : "you heard"}`;
    case "writing_sample": return `Write about the topic below for ${time}`;
    case "interactive_speaking": return "Answer the question that you hear";
    default: return `Speak about the ${step.photo ? "image" : "topic"} below for ${time}`;
  }
}

// The title and subtitle of a screen with time to prepare.
function prepTitle(step) {
  const write = step.skill === "writing";
  return [`Prepare to ${write ? "write" : "speak"} about the ${step.photo ? "image" : "topic"} below`,
    `You will have ${duration(step.answer)} to ${write ? "write" : "speak"}`];
}

// The words next to the clock while the answer time runs, as on the official screens.
function answerLabel(step) {
  if (step.type === "write_photo") return "for this question";
  if (step.skill === "writing") return "to write";
  if (step.skill === "speaking") return "to speak";
  if (step.type === "interactive_reading") return "for 6 questions";
  if (step.type === "interactive_listening") {
    return `for ${step.data.complete.length + step.data.turns.filter((t) => t.options).length} questions`;
  }
  return "for this question";
}

function heading(title, sub = "") {
  return `<h2 id="title">${title}</h2>${sub ? `<p class="sub" id="sub">${sub}</p>` : ""}`;
}

function setHeading(title) {
  $("#title").textContent = title;
  $("#sub")?.remove();
}

const CRITERIA = { content: "Content", coherence: "Coherence", grammar: "Grammar", lexis: "Vocabulary", fluency: "Fluency", pronunciation: "Pronunciation" };

// ---------- page chrome ----------

const ui = {
  app: $("#app"),
  page(html, exam = false) {
    document.body.classList.toggle("in-exam", exam);
    this.app.innerHTML = html;
    window.scrollTo(0, 0);
  },
  // An exam screen is one card, as in the official test: the clock at the top, the
  // question in the middle and the button at the bottom right.
  exam(body, wide = false) {
    this.page(`<section class="exam"><header class="head"><div class="clock" id="clock" aria-live="off">${ICON.clock}<b id="clockTime"></b><span class="lbl" id="clockLbl"></span></div></header>
      <div class="body${wide ? " wide" : ""}">${body}</div>
      <footer class="foot"><div class="foot-in"><span class="note" id="note"></span><span id="actions"></span></div></footer></section>`, true);
    this.clock(...this.clockState);
  },
  foot(actions = "", note = "") {
    gateCheck = null;
    $("#actions").innerHTML = actions;
    $("#note").innerHTML = note;
  },
  clockState: [null],
  // label: the words after the time ("for this question", "to prepare"). No seconds: label only.
  clock(label, seconds, total = Infinity) {
    this.clockState = [label, seconds, total];
    const c = $("#clock");
    if (!c) return;
    c.classList.toggle("on", label != null);
    if (label == null) return;
    $("#clockLbl").textContent = label;
    $("#clockTime").textContent = seconds == null ? "" : clockText(seconds);
    c.classList.toggle("low", seconds != null && seconds <= 10 && total > 30);
  },
  reset() {
    this.clock(null);
    onEnter = null;
  },
};

// As on the official test, the button stays gray until the screen has an answer.
// check() says whether it has one. It runs again after each input, click and selection.
let gateCheck = null;
function gate(check) {
  gateCheck = check;
  updateGate();
}
function updateGate() {
  const b = $("#actions .btn");
  if (b && gateCheck) b.disabled = !gateCheck();
}
for (const ev of ["input", "change", "click", "selectionchange"]) document.addEventListener(ev, () => setTimeout(updateGate));

// Enter presses the main button of the current screen.
let onEnter = null;
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || !onEnter || ["TEXTAREA", "SELECT", "BUTTON", "A"].includes(e.target.tagName)) return;
  if ($("#actions .btn")?.disabled) return;
  e.preventDefault();
  const fn = onEnter;
  onEnter = null;
  fn();
});

// A countdown against a fixed deadline. Resolves with the seconds used, at zero or on skip().
function countdown(seconds, label) {
  const start = performance.now(), end = start + seconds * 1000;
  let finish;
  const done = new Promise((r) => (finish = r));
  const stop = () => {
    clearInterval(timer);
    finish(Math.min(seconds, (performance.now() - start) / 1000));
  };
  const tick = () => {
    const left = (end - performance.now()) / 1000;
    ui.clock(label, left, seconds);
    if (left <= 0) stop();
  };
  const timer = setInterval(tick, 100);
  tick();
  done.skip = stop;
  return done;
}

// Show a button and resolve when the user clicks it or presses Enter.
// check: as in gate().
function waitForButton(actions, note, id = "go", check = null) {
  return new Promise((resolve) => {
    ui.foot(actions, note);
    const go = () => { onEnter = null; resolve(); };
    $(`#${id}`).onclick = go;
    onEnter = go;
    if (check) gate(check);
  });
}

function photoCredit(round, url) {
  const meta = round.photos[url.split("/").pop()];
  if (!meta) return "";
  return `<div class="credit">Photo: ${esc(meta.author)}, ${esc(meta.license)}, <a href="${esc(meta.source)}" target="_blank" rel="noopener">source</a></div>`;
}

// ---------- microphone and sound ----------

const Mic = {
  stream: null,
  ctx: null,
  analyser: null,

  async open() {
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    this.ctx = new AudioContext();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.ctx.createMediaStreamSource(this.stream).connect(this.analyser);
  },

  beep(freq = 880) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime, osc = this.ctx.createOscillator(), gain = this.ctx.createGain();
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.12, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.25);
    osc.connect(gain).connect(this.ctx.destination);
    osc.start(t);
    osc.stop(t + 0.25);
  },

  // Draw a scrolling level meter on a canvas. Returns a function that stops it.
  meter(canvas) {
    if (!canvas || !this.analyser) return () => {};
    const g = canvas.getContext("2d"), buf = new Uint8Array(this.analyser.fftSize);
    const dpr = window.devicePixelRatio || 1, bars = new Array(32).fill(0);
    const style = getComputedStyle(document.documentElement);
    const on = style.getPropertyValue("--accent").trim(), off = style.getPropertyValue("--line").trim();
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    let running = true;
    const draw = () => {
      if (!running || !canvas.isConnected) return;
      this.analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
      bars.push(Math.min(1, peak / 70));
      bars.shift();
      g.clearRect(0, 0, canvas.width, canvas.height);
      const w = canvas.width / bars.length;
      bars.forEach((v, i) => {
        const h = Math.max(6 * dpr, v * canvas.height), bw = w * 0.6;
        g.fillStyle = v > 0.08 ? on : off;
        g.beginPath();
        g.roundRect(i * w + w * 0.2, (canvas.height - h) / 2, bw, h, bw / 2);
        g.fill();
      });
      requestAnimationFrame(draw);
    };
    draw();
    return () => (running = false);
  },

  close() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
    this.stream = this.ctx = this.analyser = null;
  },

  // Start recording. Returns a function that stops and resolves with the Blob.
  record() {
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m));
    const rec = new MediaRecorder(this.stream, type ? { mimeType: type } : {});
    const chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const stopped = new Promise((r) => (rec.onstop = () => r(new Blob(chunks, { type: rec.mimeType.split(";")[0] }))));
    rec.start(1000);
    return () => {
      if (rec.state !== "inactive") rec.stop();
      return stopped;
    };
  },
};

// Play a step's spoken part once: the server's audio file, or the browser's voices without one.
const Voice = {
  audio: null,

  stop() {
    this.audio?.pause();
    window.speechSynthesis?.cancel();
  },

  // clip: the index of one line of the step (Interactive Listening plays its lines one by one).
  async play(roundId, step, clip = null) {
    const name = clip == null ? step.id : `${step.id}.${clip}`;
    const ok = await new Promise((resolve) => {
      const a = (this.audio = new Audio(`/api/audio/${roundId}/${name}.m4a`));
      a.onpause = () => resolve(true);
      a.onended = () => resolve(true);
      a.onerror = () => resolve(false);
      a.play().catch(() => resolve(false));
    });
    if (!ok) await this.speak(clip == null ? step.listen : [step.listen[clip]]);
  },

  async voices() {
    const synth = window.speechSynthesis;
    let list = synth.getVoices();
    for (let i = 0; !list.length && i < 20; i++) {
      await sleep(100);
      list = synth.getVoices();
    }
    return list.filter((v) => v.lang.startsWith("en"));
  },

  async speak(lines) {
    if (!window.speechSynthesis) return;
    const voices = await this.voices(), roles = [...new Set(lines.map((l) => l.voice))];
    for (const line of lines) {
      await new Promise((resolve) => {
        const u = new SpeechSynthesisUtterance(line.text);
        if (voices.length) u.voice = voices[roles.indexOf(line.voice) % voices.length];
        u.onend = u.onerror = resolve;
        speechSynthesis.speak(u);
      });
      await sleep(250);
    }
  },
};

// ---------- exam screens (also used by the preview route) ----------

function textBox(placeholder = "Your response") {
  return `<textarea id="box" spellcheck="false" autocorrect="off" autocapitalize="off" autocomplete="off" placeholder="${placeholder}"></textarea>`;
}

// boxed: as on the speaking screens, a box with the question in bold.
function promptBlock(step, boxed = false) {
  const bullets = step.bullets.length ? `<ul>${step.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : "";
  return boxed ? `<div class="prompt boxed"><b>${esc(step.prompt)}</b>${bullets}</div>` : `<div class="prompt">${esc(step.prompt)}${bullets}</div>`;
}

function micPanel() {
  return `<div class="mic" id="mic"><div class="state" id="micState"></div><canvas class="meter" id="meter"></canvas></div>`;
}

// Bars that move while a voice plays.
const WAVE = `<span class="wave">${"<i></i>".repeat(18)}</span>`;
// The player's wave: many thin bars of uneven height, the same on every load.
const LONG_WAVE = `<span class="wave">${Array.from({ length: 90 }, (_, i) =>
  `<i style="height:${18 + Math.round(72 * Math.abs(Math.sin(i * 1.7) * Math.sin(i * 0.31)))}%"></i>`).join("")}</span>`;

// A spoken clip without its text: a speaker and a wave, as the official test shows it.
function audioBubble(id = "") {
  return `<div class="audio talking"${id ? ` id="${id}"` : ""}>${ICON.speaker}${WAVE}</div>`;
}

// prev: {step, text} of Interactive Writing part 1, shown next to part 2.
function writeScreen(step, prev = null) {
  const [prepT, prepS] = prepTitle(step);
  const title = step.prep ? heading(prepT, prepS) : heading(screenTitle(step));
  if (step.photo) {
    return `${title}<div class="photo-row"><img class="photo" src="${esc(step.photo)}" alt="">${textBox()}</div>`;
  }
  if (step.type === "summarize_conversation") return `${title}${textBox().replace("<textarea", '<textarea class="tall"')}`;
  if (prev) {
    return `<div class="split parts">
      <div class="part done"><div class="part-h"><span class="badge">${ICON.check}</span>${screenTitle(prev.step)}</div>
        ${promptBlock(prev.step)}<div class="prev">${esc(prev.text) || "(empty)"}</div></div>
      <div class="part"><div class="part-h"><span class="badge">2</span><span id="title">${screenTitle(step)}</span></div>
        ${promptBlock(step)}${textBox()}</div></div>`;
  }
  return `${title}${promptBlock(step)}${textBox()}`;
}

function speakScreen(step) {
  const [prepT, prepS] = prepTitle(step);
  const title = step.prep ? heading(prepT, prepS) : heading(screenTitle(step));
  const what = step.photo ? `<img class="photo solo" src="${esc(step.photo)}" alt="">` : promptBlock(step, true);
  return `${title}${what}<div id="micSlot"></div>`;
}

// A spoken question or conversation that plays once.
function listenScreen(step) {
  const speaking = step.type === "interactive_speaking";
  const title = speaking ? heading(screenTitle(step), "The question plays once.") : heading("Listen to the conversation", "It plays once.");
  return `${title}<div class="talk">${audioBubble("play")}</div>${speaking ? `<div id="micSlot"></div>` : ""}`;
}

function introChips(group) {
  const step = group[0], each = `${shortDuration(step.answer)} × ${group.length}`;
  switch (step.type) {
    case "read_select": return [["Words", group.length], ["Time", `${step.answer} s each`]];
    case "fill_blanks": return [["Sentences", group.length], ["Time", `${step.answer} s each`]];
    case "read_complete": return [["Type", shortDuration(step.answer)]];
    case "listen_type": return [["Listen", "up to 3 times"], ["Type", each]];
    case "interactive_reading": return [["Questions", 6], ["Time", shortDuration(step.answer)]];
    case "interactive_listening": return [["Listen", "and answer"], ["Time", shortDuration(step.answer)]];
    case "summarize_conversation": return [[step.after ? "Prepare" : "Listen", step.after ? "none" : "once"], ["Write", shortDuration(step.answer)]];
    case "interactive_writing": return [["Prepare", `${step.prep} s`], ["Write", group.map((s) => shortDuration(s.answer)).join(" + ")]];
    case "interactive_speaking": return [["Listen", "once"], ["Speak", `${step.answer} s × ${group.length}`]];
  }
  return [["Prepare", step.prep ? `${step.prep} s` : "none"], [step.skill === "writing" ? "Write" : "Speak", shortDuration(step.answer)]];
}

function introScreen(group) {
  const step = group[0];
  // The official screen before the conversation.
  if (step.type === "interactive_speaking") {
    return `<div class="intro"><div class="icon-big">${ICON.chat}</div>
      ${heading("Prepare to have a conversation", `You will listen to ${group.length} questions and have ${step.answer} seconds to answer each`)}</div>`;
  }
  const chip = ([k, v]) => `<div class="chip"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  return `<div class="intro"><div class="icon-big">${ICON[TASK_ICON[step.type]]}</div><h1>${esc(step.name)}</h1>
    <div class="chips">${introChips(group).map(chip).join("")}</div></div>`;
}

// ---------- reading and listening screens ----------

// Text with blanks: a word to finish ({shown, len}) or a word to choose ({options}).
// A word to finish shows one box per letter. A word to choose is a numbered blank,
// filled from the numbered lists of choiceList().
function gapsHtml(segments) {
  let i = 0;
  const blank = (s) => {
    if (s.options) return `<span class="nb" data-i="${i}"><span class="num">${++i}</span><span class="w"></span></span>`;
    const shown = [...s.shown].map((c) => `<span class="cell">${esc(c)}</span>`).join("");
    const empty = '<input class="cell" spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off">'.repeat(s.len);
    return `<span class="letters" data-i="${i++}">${shown}${empty}</span>`;
  };
  return segments.map((s, n) => {
    if (typeof s === "string") return esc(typeof segments[n - 1] === "object" ? s.replace(/^\S+/, "") : s);
    // Punctuation right after a blank stays on the blank's line.
    const next = segments[n + 1];
    return `<span class="nowrap">${blank(s)}${esc(typeof next === "string" ? next.match(/^\S*/)[0] : "")}</span>`;
  }).join("");
}

// The letter boxes act as one text field: typing moves on, Backspace moves back.
function wireGaps(root) {
  const cells = [...root.querySelectorAll("input.cell")];
  cells.forEach((c, i) => {
    c.addEventListener("focus", () => c.select());
    // One letter per box. A paste or fast typing fills the next boxes.
    c.addEventListener("input", () => {
      const typed = [...c.value];
      if (typed.length > 1 && c.dataset.v) typed.splice(typed.indexOf(c.dataset.v), 1);
      let j = i;
      for (const ch of typed.length ? typed : [""]) {
        if (!cells[j]) break;
        cells[j].value = cells[j].dataset.v = ch;
        j++;
      }
      if (typed.length) (cells[j] || cells[j - 1]).focus();
    });
    c.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !c.value && cells[i - 1]) {
        e.preventDefault();
        cells[i - 1].value = cells[i - 1].dataset.v = "";
        cells[i - 1].focus();
      } else if (e.key === "ArrowLeft" && cells[i - 1]) cells[i - 1].focus();
      else if (e.key === "ArrowRight" && cells[i + 1]) cells[i + 1].focus();
    });
  });
  return () => [...root.querySelectorAll(".letters")].map((w) => [...w.querySelectorAll("input")].map((x) => x.value).join(""));
}

// Options with a radio circle, of which the user picks one. Returns a getter for the picked text.
function options(list, onPick = () => {}) {
  const id = `o${Math.random().toString(36).slice(2, 8)}`;
  const html = `<div class="options" id="${id}">${list.map((o) => `<button class="opt" type="button">${esc(o)}</button>`).join("")}</div>`;
  let picked = "";
  const wire = () => $(`#${id}`).querySelectorAll(".opt").forEach((b, i) => (b.onclick = () => {
    $(`#${id}`).querySelectorAll(".opt").forEach((x) => x.classList.toggle("on", x === b));
    picked = list[i];
    onPick(picked);
  }));
  return { html, wire, get: () => picked };
}

function readSelectScreen(step) {
  return `${heading(screenTitle(step))}<div class="word">${esc(step.data.word)}</div>
    <div class="tiles"><button class="tile" id="yes" type="button">${ICON.check}<span>Yes</span></button><button class="tile" id="no" type="button">${ICON.cross}<span>No</span></button></div>`;
}

function gapScreen(step) {
  const title = step.data.title ? `<h3 class="ptitle">${esc(step.data.title)}</h3>` : "";
  const kind = step.type === "fill_blanks" ? "one" : "para";
  return `${heading(screenTitle(step))}<div class="gaptext ${kind}">${title}${gapsHtml(step.data.segments)}</div>`;
}

function listenTypeScreen(step) {
  return `${heading(screenTitle(step))}<div class="lt"><button class="sq" id="play" type="button">${ICON.speaker}</button>
    <div class="replays" id="plays">Replays left: 2</div></div>${textBox()}`;
}

// Interactive Reading: the passage on the left, the question on the right.
function readingScreen(passage, title, right) {
  return `<div class="split ir"><div class="panel"><div class="label">Passage</div><div class="ptext" id="text">${passage}</div></div>
    <div class="qs"><h2>${title}</h2>${right}</div></div>`;
}

// The numbered word lists of Complete the Sentences.
function choiceList(segments) {
  return `<div class="picks">${segments.filter((s) => s.options).map((s, i) => `<label class="pickrow"><span class="num">${i + 1}</span>
    <select class="pick" data-i="${i}"><option value="">Select a word</option>${s.options.map((o) => `<option>${esc(o)}</option>`).join("")}</select></label>`).join("")}</div>`;
}

function readingWordsScreen(step) {
  return readingScreen(gapsHtml(step.data.passage), "Select the best option for each missing word", choiceList(step.data.passage));
}

// The first part of an Interactive Reading text, with the right words filled in.
function firstPart(step) {
  let i = 0;
  return step.data.passage.map((s) => (typeof s === "string" ? esc(s) : esc(step.key.choices[i++]))).join("");
}

// Listen and Complete: an audio player, then one sentence to complete per question.
function listeningScreen(step) {
  const qs = step.data.questions || [];
  const items = step.data.complete.map(([a, b], i) => `<li>${qs[i] ? `<div class="lcq">${esc(qs[i])}</div>` : ""}<div class="sentbox">${esc(a)}<input class="line" data-i="${i}" spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off">${esc(b)}</div></li>`).join("");
  return `${heading("Listen to the scenario and then answer questions")}
    <div class="player" id="player"><button class="pbtn" id="play" type="button">${ICON.play}</button>${LONG_WAVE}</div><ol class="lc">${items}</ol>`;
}

// ---------- the exam ----------

let activeExam = null;
window.addEventListener("beforeunload", (e) => {
  if (activeExam) e.preventDefault();
});

const SECTION_NAMES = { reading: "Reading", listening: "Listening", writing: "Writing", speaking: "Speaking" };

class Exam {
  constructor(round, section = "") {
    this.round = round;
    this.section = SECTION_NAMES[section] ? section : "";
    this.steps = this.section ? round.steps.filter((s) => s.section === this.section) : round.steps;
    if (!this.steps.length) throw new Error(`This round has no ${section} tasks.`);
    this.answers = {};
    this.attemptId = null;
    this.hash = location.hash;
  }

  // Consecutive steps of one type share an intro screen (three photos, two IW parts, all IS questions).
  group(i) {
    const out = [];
    for (let j = i; j < this.steps.length && this.steps[j].type === this.steps[i].type; j++) out.push(this.steps[j]);
    return out;
  }

  async setup() {
    ui.reset();
    const tasks = [];
    this.steps.forEach((s, i) => { if (i === 0 || s.task !== this.steps[i - 1].task) tasks.push([s, i]); });
    const minutes = this.section ? this.round.sections[this.section].minutes : this.round.minutes;
    const needsMic = this.steps.some((s) => s.skill === "speaking");
    ui.exam(`<h1>${esc(this.round.title)}</h1>
      <p class="muted">${this.section ? `${SECTION_NAMES[this.section]} only · ` : ""}${plural(this.steps.length, "question")} · about ${minutes} min</p>
      ${needsMic ? "" : `<p>No microphone needed.</p>`}
      <div class="mic" style="margin:28px 0 18px${needsMic ? "" : ";display:none"}">
        <div class="state" id="micState">${ICON.mic.replace("<svg", '<svg width="28" height="28"')}</div>
        <canvas class="meter" id="meter"></canvas>
        <div id="micHint"></div>
      </div>
      <details class="adv"><summary>Start from a later task</summary>
        <p style="margin-top:12px"><select id="from">${tasks.map(([s, i]) => `<option value="${i}">${i + 1}. ${esc(s.name)}</option>`).join("")}</select></p>
      </details>`);
    if (!needsMic) {
      await waitForButton(`<button class="btn ok" id="go">Begin</button>`);
      return Number($("#from").value);
    }
    for (;;) {
      await waitForButton(`<button class="btn" id="go">Allow microphone</button>`, "");
      try {
        await Mic.open();
        break;
      } catch {
        $("#micHint").innerHTML = `<span class="err">The browser blocked the microphone. Allow it in the address bar, then try again.</span>`;
      }
    }
    Mic.meter($("#meter"));
    $("#micState").innerHTML = `<span style="color:var(--ok)">${ICON.check.replace("<svg", '<svg width="28" height="28"')}</span>`;
    await waitForButton(`<button class="btn ok" id="go">Begin</button>`);
    return Number($("#from").value);
  }

  async run() {
    const from = await this.setup();
    activeExam = this;
    this.attemptId = (await api.post("/api/attempts", { round: this.round.id, section: this.section })).id;
    for (let i = from; i < this.steps.length; i++) {
      const step = this.steps[i];
      if (i === from || step.type !== this.steps[i - 1].type) {
        ui.clock(null);
        ui.exam(introScreen(this.group(i)));
        await waitForButton(`<button class="btn" id="go">Start</button>`);
      }
      await this.run_step(step);
    }
    await api.post(`/api/attempts/${this.attemptId}/finish`);
    activeExam = null;
    Mic.close();
    this.finished();
  }

  run_step(step) {
    const special = {
      read_select: this.readSelect, fill_blanks: this.gaps, read_complete: this.gaps,
      listen_type: this.listenType, interactive_reading: this.reading, interactive_listening: this.listening,
    }[step.type];
    return (special || (step.skill === "writing" ? this.write : this.speak)).call(this, step);
  }

  // Run a timed screen. body(time) does the work and resolves early when the user is done.
  async timed(step, label, body) {
    const time = countdown(step.answer, label);
    await Promise.race([time, body(time)]);
    Voice.stop();
    const used = await (time.skip(), time);
    ui.clock(null);
    return used;
  }

  async readSelect(step) {
    ui.exam(readSelectScreen(step));
    let real = null;
    const used = await this.timed(step, answerLabel(step), () => new Promise((done) => {
      ui.foot("");
      $("#yes").onclick = () => { real = true; done(); };
      $("#no").onclick = () => { real = false; done(); };
    }));
    await this.save(step, { real }, "application/json", used);
  }

  async gaps(step) {
    ui.exam(gapScreen(step));
    const values = wireGaps($(".gaptext"));
    $("input.cell")?.focus();
    // Enter submits one sentence, but not a whole paragraph by accident.
    const go = `<button class="btn" id="go">Continue</button>`, typed = () => values().some(Boolean);
    const used = await this.timed(step, answerLabel(step), () => (step.type === "fill_blanks"
      ? waitForButton(go, "", "go", typed)
      : new Promise((done) => { ui.foot(go); $("#go").onclick = done; gate(typed); })));
    await this.save(step, { missing: values() }, "application/json", used);
  }

  async listenType(step) {
    ui.exam(listenTypeScreen(step));
    let plays = 3, playing = false;
    const play = async () => {
      if (!plays || playing) return;
      playing = true;
      plays--;
      $("#play").classList.add("talking");
      await Voice.play(this.round.id, step);
      if (!$("#play")) return;
      playing = false;
      $("#play").classList.remove("talking");
      $("#plays").textContent = `Replays left: ${plays}`;
      $("#play").disabled = !plays;
    };
    $("#play").onclick = play;
    const used = await this.timed(step, answerLabel(step), () => {
      play();
      $("#box").focus();
      return new Promise((done) => {
        ui.foot(`<button class="btn" id="skip">Continue</button>`);
        $("#skip").onclick = done;
        gate(() => $("#box").value.trim());
      });
    });
    await this.save(step, { text: $("#box").value, plays: 3 - plays }, "application/json", used);
  }

  async reading(step) {
    const d = step.data, ans = { choices: [], missing: "", highlight: ["", ""], idea: "", title: "" };
    const draft = setInterval(() => this.post(step, ans, "application/json", false).catch(() => {}), 5000);
    const next = (check) => waitForButton(`<button class="btn" id="go">Continue</button>`, "", "go", check);
    const full = esc(step.key.full_text);
    const used = await this.timed(step, answerLabel(step), async () => {
      ui.exam(readingWordsScreen(step), true);
      const picks = [...document.querySelectorAll(".pick")];
      picks.forEach((s, i) => (s.onchange = () => {
        ans.choices = picks.map((x) => x.value);
        $(`.nb[data-i="${i}"] .w`).textContent = s.value;
        $(`.nb[data-i="${i}"]`).classList.toggle("on", !!s.value);
      }));
      await next(() => picks.some((x) => x.value));
      ans.choices = picks.map((x) => x.value);

      const choice = options(d.missing_options, (v) => {
        $("#blank").textContent = v;
        $("#blank").classList.add("on");
      });
      ui.exam(readingScreen(`${firstPart(step)} <span class="blank" id="blank"></span> ${esc(d.rest)}`,
        "Select the best sentence to complete the passage", choice.html), true);
      choice.wire();
      await next(choice.get);
      ans.missing = choice.get();

      // One listener for both questions: a selection always answers the question on screen.
      let q = 0;
      const track = () => {
        const sel = window.getSelection(), text = $("#text");
        if (text && sel.rangeCount && text.contains(sel.anchorNode) && sel.toString().trim()) {
          ans.highlight[q] = sel.toString().trim();
          $("#mark").textContent = ans.highlight[q];
          $("#mark").classList.add("on");
        }
      };
      document.addEventListener("selectionchange", track);
      for (; q < 2; q++) {
        window.getSelection().removeAllRanges();
        ui.exam(readingScreen(full, "Highlight text in the passage to answer the question below",
          `<p class="q">${esc(d.highlight[q])}</p><div class="hlbox" id="mark">Click and drag to highlight text</div>`), true);
        $("#text").classList.add("hl");
        await next(() => ans.highlight[q]);
      }
      document.removeEventListener("selectionchange", track);
      window.getSelection().removeAllRanges();

      for (const [key, title, list] of [["idea", "Select the idea that is expressed in the passage", d.idea_options], ["title", "Select the best title for the passage", d.title_options]]) {
        const pick = options(list, (v) => (ans[key] = v));
        ui.exam(readingScreen(full, title, pick.html), true);
        pick.wire();
        await next(pick.get);
      }
    });
    clearInterval(draft);
    await this.save(step, ans, "application/json", used);
  }

  async listening(step) {
    const d = step.data, ans = { complete: d.complete.map(() => ""), turns: [] };
    const draft = setInterval(() => this.post(step, ans, "application/json", false).catch(() => {}), 5000);
    const used = await this.timed(step, answerLabel(step), async () => {
      ui.exam(listeningScreen(step));
      let playing = false;
      $("#play").onclick = async () => {
        if (playing) return;
        playing = true;
        $("#player").classList.add("talking");
        await Voice.play(this.round.id, step, 0);
        playing = false;
        $("#player")?.classList.remove("talking");
      };
      const inputs = [...document.querySelectorAll(".lc .line")];
      inputs.forEach((x, i) => (x.oninput = () => (ans.complete[i] = x.value)));
      $("#play").click();
      await waitForButton(`<button class="btn" id="go">Continue</button>`, "", "go", () => inputs.some((x) => x.value.trim()));

      ui.exam(`${heading("Participate in a conversation about this scenario")}<p class="lead">Listen closely! Audio clips only play once.</p>
        <div class="chat" id="chat"></div><div id="choose"></div>`);
      const say = (who, html) => $("#chat").insertAdjacentHTML("beforeend", `<div class="bubble ${who}">${html}</div>`);
      let n = 0;
      for (const turn of d.turns) {
        if (turn.clip != null) {
          say("them", audioBubble());
          ui.foot(`<button class="btn" disabled>Continue</button>`);
          await Voice.play(this.round.id, step, turn.clip);
          $("#chat .bubble:last-child .audio")?.classList.remove("talking");
          continue;
        }
        const right = step.key.turns[n];
        const pick = options(turn.options);
        $("#choose").innerHTML = `<h3 class="qtitle">Select the best response</h3>${pick.html}`;
        pick.wire();
        await new Promise((done) => {
          ui.foot(`<button class="btn" id="go">Continue</button>`);
          $("#go").onclick = () => pick.get() && done();
          gate(pick.get);
        });
        ans.turns[n++] = pick.get();
        const ok = pick.get() === right;
        $("#choose").innerHTML = "";
        say(`you ${ok ? "ok" : "bad"}`, `<span class="mark">${ok ? ICON.check : ICON.cross}</span>${esc(right)}`);
      }
      await waitForButton(`<button class="btn" id="go">Continue</button>`);
    });
    clearInterval(draft);
    await this.save(step, ans, "application/json", used);
  }

  async listen(step) {
    ui.clock("listening");
    ui.foot(`<button class="btn" disabled>Continue</button>`);
    await Voice.play(this.round.id, step);
    $("#play").classList.remove("talking");
  }

  // Part 1 of Interactive Writing, shown next to part 2.
  previous(step) {
    const s = this.steps.find((x) => x.id === step.show_previous);
    return s ? { step: s, text: this.answers[s.id] ?? "" } : null;
  }

  async write(step) {
    if (step.type === "summarize_conversation" && !step.after) {
      ui.exam(listenScreen(step));
      await this.listen(step);
    }
    ui.exam(writeScreen(step, step.show_previous ? this.previous(step) : null), !!step.photo || !!step.show_previous);
    const box = $("#box");
    if (step.prep) {
      box.disabled = true;
      const prep = countdown(step.prep, "to prepare");
      ui.foot(`<button class="btn" id="skip">Start writing</button>`);
      $("#skip").onclick = prep.skip;
      await prep;
      setHeading(screenTitle(step));
    }
    box.disabled = false;
    box.focus();
    Mic.beep();
    const draft = setInterval(() => this.post(step, box.value, "text/plain", false).catch(() => {}), 5000);
    const answer = countdown(step.answer, answerLabel(step));
    ui.foot(`<button class="btn" id="skip">Continue</button>`);
    $("#skip").onclick = answer.skip;
    gate(() => box.value.trim());
    const used = await answer;
    clearInterval(draft);
    box.disabled = true;
    Mic.beep(660);
    ui.clock(null);
    this.answers[step.id] = box.value;
    await this.save(step, box.value, "text/plain", used);
  }

  async speak(step) {
    if (step.type === "interactive_speaking") {
      ui.exam(listenScreen(step));
      await this.listen(step);
    } else {
      ui.exam(speakScreen(step));
    }
    if (step.prep) {
      const prep = countdown(step.prep, "to prepare");
      ui.foot(`<button class="btn" id="skip">${ICON.mic}Record now</button>`);
      $("#skip").onclick = prep.skip;
      await prep;
      setHeading(screenTitle(step));
    }
    Mic.beep();
    $("#micSlot").innerHTML = micPanel();
    $("#micState").innerHTML = `<span class="dot"></span> Recording`;
    $("#mic").classList.add("rec");
    const stopMeter = Mic.meter($("#meter"));
    const stop = Mic.record();
    const answer = countdown(step.answer, answerLabel(step));
    ui.foot(`<button class="btn bad" id="skip">Stop</button>`);
    $("#skip").onclick = answer.skip;
    const used = await answer;
    const blob = await stop();
    stopMeter();
    Mic.beep(660);
    ui.clock(null);
    $("#micState").innerHTML = `<span style="color:var(--ok)">✓</span>`;
    $("#mic").classList.remove("rec");
    await this.save(step, blob, blob.type, used);
  }

  post(step, body, type, final, seconds) {
    const q = final ? `?final=1&seconds=${seconds.toFixed(1)}` : "?final=0";
    return api.post(`/api/attempts/${this.attemptId}/steps/${step.id}${q}`, body, type);
  }

  // Save a final answer. On failure keep the answer in memory and offer a retry.
  async save(step, body, type, seconds) {
    for (;;) {
      ui.foot(`<button class="btn" disabled>Saving</button>`, "");
      try {
        await this.post(step, body, type, true, seconds);
        return;
      } catch {
        await waitForButton(`<button class="btn" id="go">Try again</button>`,
          `<span class="err">Could not save this answer. Check that det-coach is still running.</span>`);
      }
    }
  }

  finished() {
    ui.clock(null);
    ui.exam(`<div class="icon-big ok">${ICON.check}</div><h1>Round complete</h1>
      <p>For feedback, tell your coding agent:</p><div class="prompt">Grade my latest det-coach attempt.</div>`);
    ui.foot(`<a class="btn ok" href="#/attempt/${this.attemptId}" id="go">See results</a>`);
    onEnter = () => (location.hash = `#/attempt/${this.attemptId}`);
  }
}

// ---------- home ----------

async function showHome() {
  ui.reset();
  const [rounds, attempts] = await Promise.all([api.get("/api/rounds"), api.get("/api/attempts")]);
  const statusText = { graded: "Feedback ready", awaiting_feedback: "Awaiting feedback", in_progress: "Not finished" };
  const titles = Object.fromEntries(rounds.map((r) => [r.id, r.title]));
  ui.page(`<section class="hero">
      <h1>Duolingo English Test practice, with feedback</h1>
      <ol class="steps">
        <li><span><b>Take a round</b> with the official timings.</span></li>
        <li><span><b>Tell your coding agent:</b> “Grade my latest det-coach attempt.”</span></li>
        <li><span><b>Read the feedback</b> here.</span></li>
      </ol>
    </section>
    <div class="section-h">Rounds</div>
    <div class="rounds">${rounds.map((r) => `
      <section class="box round">
        <h3>${esc(r.title)}</h3>
        <div class="meta">${plural(r.steps, "question")} · about ${r.minutes} min</div>
        <a class="btn small" href="#/exam/${esc(r.id)}">Start</a>
        ${Object.keys(r.sections).length > 1 ? `<div class="sections"><span class="lbl">Or one section</span>${Object.entries(r.sections).map(([k, v]) => `
          <a href="#/exam/${esc(r.id)}/${k}" title="${plural(v.steps, "question")} · about ${v.minutes} min">${SECTION_NAMES[k]}<span>${v.minutes} min</span></a>`).join("")}</div>` : ""}
      </section>`).join("") || `<section class="box empty">No rounds found in rounds/.</section>`}
    </div>
    <div class="section-h">Your attempts</div>
    <section class="box">${attempts.map((a) => `
      <a class="row" href="#/attempt/${esc(a.id)}">
        <span class="grow"><span class="id">${esc(titles[a.round] || a.round)}${a.section ? ` · ${SECTION_NAMES[a.section] || esc(a.section)}` : ""}</span><br><span class="muted">${when(a.started)} · ${plural(a.steps, "answer")}</span></span>
        <span class="pill ${a.status}">${statusText[a.status]}</span>
      </a>`).join("") || `<div class="empty">No attempts yet. Start a round above.</div>`}
    </section>
    <p class="fine">det-coach is an independent open source project. It is not affiliated with or endorsed by Duolingo. Its score bands are estimates, not official scores.</p>`);
}

// ---------- results ----------

function bandRange([lo, hi]) {
  return esc(lo === hi ? `${lo}` : `${lo} to ${hi}`);
}

function scale([lo, hi]) {
  const pos = (v) => ((v - 10) / 150) * 100;
  return `<div class="scale"><span style="left:${pos(lo)}%;width:${pos(hi) - pos(lo)}%"></span></div><small>${bandRange([lo, hi])}</small>`;
}

function metricsRow(m) {
  if (!m || m.silent) return `<div class="metrics"><span class="metric">No speech found in the recording</span></div>`;
  const items = [
    ["words per minute", m.words_per_minute],
    ["words", m.words],
    ["pauses over 2 s", m.pauses_over_2s],
    ["longest pause", `${m.longest_pause_seconds} s`],
    [m.fillers === 1 ? "filler" : "fillers", m.fillers],
    ["time used", `${Math.round(m.slot_used * 100)}%`],
  ];
  return `<div class="metrics">${items.map(([k, v]) => `<span class="metric"><b>${esc(v)}</b> ${k}</span>`).join("")}</div>`;
}

function stepContext(round, step) {
  const parts = [];
  if (step.photo) parts.push(`<img class="thumb" src="${esc(step.photo)}" alt="">${photoCredit(round, step.photo)}`);
  if (step.prompt) parts.push(promptBlock(step));
  if (step.type === "interactive_speaking") parts.push(`<div class="prompt"><span class="label">The interviewer asked</span><br>${esc(step.listen[0].text)}</div>`);
  if (step.type === "summarize_conversation") {
    parts.push(`<details class="model"><summary>Show the conversation</summary><div>${step.listen.map((l) => `<b>${esc(l.voice)}:</b> ${esc(l.text)}`).join("\n")}</div></details>`);
  }
  return parts.join("");
}

function stepAnswer(d, step) {
  if (step.skill === "writing") {
    const text = d.answers[step.id] ?? "";
    const draft = d.manifest.steps[step.id] ? "" : " · autosaved, not submitted";
    return `<div class="label">Your answer · ${plural(wordCount(text), "word")}${draft}</div><div class="answer">${esc(text) || "(empty)"}</div>`;
  }
  const t = d.transcripts[step.id];
  const audio = d.recordings[step.id] ? `<audio controls preload="none" src="${esc(d.recordings[step.id])}"></audio>` : "";
  if (!t) return `<div class="label">Your recording</div>${audio}<p class="muted">Not transcribed yet. The grader transcribes it.</p>`;
  const marked = esc(t.marked || t.text).replace(/\[(\d+(?:\.\d)?) s\]/g, '<span class="pause">(pause $1 s)</span>');
  return `<div class="label">Your recording</div>${audio}<div class="answer">${marked || "(silence)"}</div>${metricsRow(t.metrics)}`;
}

function stepFeedback(f, step) {
  if (!f) return "";
  const crit = Object.entries(f.criteria || {}).map(([k, v]) => `<div class="crit"><div class="name">${CRITERIA[k] || esc(k)}</div>${v
    ? `<div>${scale(v.band)}</div><div>${esc(v.note)}</div>`
    : `<div></div><div class="muted">Not judged. The grader reads a transcript and cannot hear you.</div>`}</div>`).join("");
  const list = (title, items) => (items?.length ? `<div class="label">${title}</div><ul class="plain">${items.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : "");
  const fixes = (f.fixes || []).map((x) => `<div class="fix"><span class="was">${esc(x.original)}</span><span class="now">${esc(x.better)}</span><span class="why">${esc(x.why)}</span></div>`).join("");
  const model = f.model_answer ? `<details class="model"><summary>A stronger answer</summary><div>${esc(f.model_answer)}</div></details>` : "";
  return `<div class="label" style="margin-top:18px">Feedback</div><div class="criteria">${crit}</div>
    ${list("What worked", f.strengths)}${fixes ? `<div class="label">Fixes</div>${fixes}` : ""}${list("Next time", f.next_time)}${model}`;
}

const GRADED = new Set(["writing", "speaking"]);

function creditMark(c) {
  if (c >= 1) return `<span class="ok">${ICON.check}</span>`;
  if (c <= 0) return `<span class="no">${ICON.cross}</span>`;
  return `<b>${Math.round(c * 100)}%</b>`;
}

// One box per reading or listening task, with every item that det-coach scored.
function scoredTask(d, steps) {
  const items = steps.flatMap((s) => d.scores[s.id]?.items || []);
  const credit = items.reduce((a, x) => a + x.credit, 0);
  const rows = items.map((x) => `<tr><td>${esc(x.prompt)}</td><td>${esc(x.given) || '<span class="muted">(none)</span>'}</td><td>${esc(x.key)}</td><td class="c">${creditMark(x.credit)}</td></tr>`).join("");
  return `<section class="box step" id="step-${esc(steps[0].task)}">
    <div class="step-h"><h3>${esc(steps[0].name)}</h3><span class="band">${+credit.toFixed(1)} of ${items.length}</span></div>
    <div class="table"><table class="items"><thead><tr><th>Question</th><th>Your answer</th><th>Answer</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

function resultsPage(d) {
  const { round, feedback: fb, manifest } = d;
  const answered = round.steps.filter((s) => manifest.steps[s.id]);
  const shown = round.steps.filter((s) => manifest.steps[s.id] || d.answers[s.id] != null);
  let head = `<h1>${esc(round.title)}</h1>
    <div class="muted">${manifest.section ? `${SECTION_NAMES[manifest.section] || esc(manifest.section)} only · ` : ""}${when(manifest.started)} · ${plural(answered.length, "answer")} of ${round.steps.filter((s) => !manifest.section || s.section === manifest.section).length}</div>`;
  const share = (k) => (d.skills?.[k] ? `<div class="score"><div class="k">${k[0].toUpperCase() + k.slice(1)} points</div><div class="v">${Math.round(d.skills[k].share * 100)}%</div></div>` : "");
  const shares = share("reading") + share("listening");
  if (fb) {
    const score = (k, label) => (fb.estimate?.[k] ? `<div class="score"><div class="k">${label}</div><div class="v">${bandRange(fb.estimate[k])}</div></div>` : "");
    head += `<div class="scores">${shares}${score("writing", "Writing estimate")}${score("speaking", "Speaking estimate")}</div>
      <p class="disclaimer">Estimated by ${esc(fb.grader)} from the official scoring guide. These are not official scores.</p>
      <p style="margin-top:16px">${esc(fb.summary)}</p>
      <h3 style="margin-top:22px">Top priorities</h3>
      <ol class="steps">${fb.priorities.map((p) => `<li><span><b>${esc(p.title)}.</b> ${esc(p.detail)}</span></li>`).join("")}</ol>`;
  } else if (shares) {
    head += `<div class="scores">${shares}</div>`;
  }
  if (shares) head += `<p class="disclaimer">det-coach scores reading and listening itself. The real test adapts these questions to you, so a share of points is not a DET score.</p>`;
  const waiting = fb ? "" : d.status === "in_progress"
    ? `<section class="box waiting"><h3>This attempt is not finished</h3>
        <p>You can still get feedback on the saved answers. Ask your coding agent: <b>“Grade det-coach attempt ${esc(manifest.id)}.”</b></p></section>`
    : `<section class="box waiting"><h3>Waiting for feedback</h3>
        <p>Ask your coding agent in this project folder: <b>“Grade my latest det-coach attempt.”</b></p>
        <p class="muted">The agent runs <code>det-coach packet ${esc(manifest.id)}</code>, grades each answer and writes <code>feedback.json</code>. This page updates by itself.</p></section>`;
  const steps = shown.map((s, i) => {
    if (!GRADED.has(s.skill)) {
      if (i > 0 && shown[i - 1].task === s.task) return "";
      return scoredTask(d, shown.filter((x) => x.task === s.task));
    }
    const f = fb?.steps?.[s.id];
    return `<section class="box step" id="step-${esc(s.id)}">
      <div class="step-h"><h3>${esc(s.name)}${s.part ? ` <span class="muted">· ${esc(s.part)}</span>` : ""}</h3>${f ? `<span class="band">${bandRange(f.band)}</span>` : ""}</div>
      ${stepContext(round, s)}${stepAnswer(d, s)}${stepFeedback(f, s)}</section>`;
  }).join("");
  const remove = `<section class="danger"><div><b>Delete this attempt</b>
    <p class="muted">Removes its answers, recordings and feedback from this computer. You cannot undo this.</p></div>
    <button class="btn ghost small" id="delete" type="button">Delete</button></section>`;
  return `<section class="res-head">${head}</section>${waiting}${steps}${remove}`;
}

function wireDelete(id) {
  $("#delete").onclick = async () => {
    if (!confirm(`Delete attempt ${id}? Its answers, recordings and feedback are removed for good.`)) return;
    try {
      await api.del(`/api/attempts/${id}`);
      location.hash = "#/";
    } catch (e) {
      alert(`Could not delete the attempt: ${e.message}`);
    }
  };
}

async function showAttempt(id, token) {
  ui.reset();
  let d = await api.get(`/api/attempts/${id}`);
  ui.page(resultsPage(d));
  wireDelete(id);
  // Wait for the grader: refresh once feedback.json appears.
  while (d.status !== "graded" && token === routeToken) {
    await sleep(4000);
    if (token !== routeToken) return;
    const next = await api.get(`/api/attempts/${id}`).catch(() => d);
    if (next.status !== d.status) {
      ui.page(resultsPage(next));
      wireDelete(id);
    }
    d = next;
  }
}

// ---------- preview: one exam screen, frozen, for screenshots and round authors ----------

// The later screens of Interactive Reading and Interactive Listening, for the preview route.
function laterScreen(step, stage) {
  const d = step.data, full = esc(step.key.full_text);
  const pick = (list) => options(list).html;
  switch (`${step.type}/${stage}`) {
    case "interactive_reading/missing": return readingScreen(`${firstPart(step)} <span class="blank"></span> ${esc(d.rest)}`, "Select the best sentence to complete the passage", pick(d.missing_options));
    case "interactive_reading/highlight": return readingScreen(full, "Highlight text in the passage to answer the question below", `<p class="q">${esc(d.highlight[0])}</p><div class="hlbox">Click and drag to highlight text</div>`);
    case "interactive_reading/idea": return readingScreen(full, "Select the idea that is expressed in the passage", pick(d.idea_options));
    case "interactive_reading/title": return readingScreen(full, "Select the best title for the passage", pick(d.title_options));
    case "interactive_listening/respond": return `${heading("Participate in a conversation about this scenario")}<p class="lead">Listen closely! Audio clips only play once.</p>
      <div class="chat"><div class="bubble them">${audioBubble().replace(" talking", "")}</div></div><div id="choose"><h3 class="qtitle">Select the best response</h3>${pick(d.turns.find((t) => t.options).options)}</div>`;
  }
  throw new Error(`No stage ${stage} for ${step.id}`);
}

async function showPreview(roundId, stepId, stage = "") {
  ui.reset();
  const round = await api.get(`/api/rounds/${roundId}`);
  const step = round.steps.find((s) => s.id === stepId);
  if (!step) throw new Error(`No step ${stepId} in ${roundId}`);
  const prev = round.steps.find((s) => s.id === step.show_previous);
  const screen = {
    read_select: readSelectScreen, fill_blanks: gapScreen, read_complete: gapScreen,
    listen_type: listenTypeScreen, interactive_reading: readingWordsScreen,
    interactive_listening: listeningScreen, interactive_speaking: listenScreen,
  }[step.type];
  if (stage) ui.exam(laterScreen(step, stage), step.type === "interactive_reading");
  else if (screen) ui.exam(screen(step), step.type === "interactive_reading");
  else if (step.skill === "speaking") ui.exam(speakScreen(step));
  else ui.exam(writeScreen(step, prev ? { step: prev, text: "(your answer to part 1)" } : null), !!step.photo || !!prev);
  wireGaps($("#app"));
  const t = step.prep || step.answer;
  ui.clock(step.prep ? "to prepare" : answerLabel(step), t, t);
  if (step.type === "read_select") ui.foot("");
  else if (step.skill === "speaking" && step.prep) ui.foot(`<button class="btn">${ICON.mic}Record now</button>`);
  else ui.foot(`<button class="btn" disabled>Continue</button>`);
}

// ---------- router ----------

let routeToken = 0;

async function route() {
  const token = ++routeToken;
  const [, view, a, b, c] = location.hash.replace(/^#\/?/, "/").split("/").map(decodeURIComponent);
  try {
    if (view === "exam" && a) await new Exam(await api.get(`/api/rounds/${a}`), b).run();
    else if (view === "attempt" && a) await showAttempt(a, token);
    else if (view === "preview" && a && b) await showPreview(a, b, c);
    else await showHome();
  } catch (e) {
    activeExam = null;
    ui.reset();
    ui.page(`<section class="hero"><h1>Something went wrong</h1><p class="err">${esc(e.message)}</p>
      <p>Check that <code>det-coach practice</code> is still running, then <a href="#/">go home</a>.</p></section>`);
  }
}

window.addEventListener("hashchange", () => {
  if (activeExam) {
    if (!confirm("Leave the exam? Answers you finished stay saved.")) {
      history.replaceState(null, "", activeExam.hash);
      return;
    }
    // A reload is the clean way to stop every timer, recorder and sound of the exam.
    activeExam = null;
    location.reload();
    return;
  }
  route();
});
route();
