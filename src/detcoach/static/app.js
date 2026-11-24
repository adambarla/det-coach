"use strict";
/*
 * det-coach practice app. Plain JavaScript, no build step, no dependencies.
 *
 * Routes
 *   #/                       home: rounds and past attempts
 *   #/exam/<round>           take a round with the official timings
 *   #/attempt/<id>           answers, recordings, transcripts and feedback
 *   #/preview/<round>/<step> one exam screen without timers (screenshots, round authors)
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
  if (s <= 90) return `${s} seconds`;
  const m = Math.floor(s / 60), r = s % 60;
  return r ? `${m} min ${r} s` : plural(m, "minute");
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
};

const ICON = {
  pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/></svg>',
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/></svg>',
  ear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 14v-2a9 9 0 0 1 18 0v2"/><rect x="2" y="14" width="5" height="7" rx="2"/><rect x="17" y="14" width="5" height="7" rx="2"/></svg>',
  speaker: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path fill="none" d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
};

const TASK_ICON = {
  write_photo: "pen", interactive_writing: "pen", summarize_conversation: "ear", writing_sample: "pen",
  speak_photo: "mic", read_then_speak: "mic", interactive_speaking: "chat", speaking_sample: "mic",
};

function screenTitle(step) {
  switch (step.type) {
    case "write_photo": return "Write one or more sentences that describe the photo.";
    case "interactive_writing": return step.show_previous ? "Now answer a follow-up question on the same topic." : "Read the question and write your answer.";
    case "summarize_conversation": return `Summarize the conversation in ${duration(step.answer)}.`;
    case "writing_sample": return `Write about the topic below for ${duration(step.answer)}.`;
    case "interactive_speaking": return "Listen and answer. The question plays once.";
    default: return `Speak about the ${step.photo ? "photo" : "topic below"} for up to ${duration(step.answer)}.`;
  }
}

const CRITERIA = { content: "Content", coherence: "Coherence", grammar: "Grammar", lexis: "Vocabulary", fluency: "Fluency", pronunciation: "Pronunciation" };

// ---------- page chrome ----------

const ui = {
  app: $("#app"),
  page(html) {
    this.app.innerHTML = html;
    window.scrollTo(0, 0);
  },
  exam(body, wide = false) {
    this.page(`<section class="exam"><div class="body${wide ? " wide" : ""}">${body}</div>
      <footer class="foot"><div class="foot-in"><span class="note" id="note"></span><span id="actions"></span></div></footer></section>`);
  },
  foot(actions = "", note = "") {
    $("#actions").innerHTML = actions;
    $("#note").innerHTML = note;
  },
  progress(done, total) {
    $("#track").hidden = total == null;
    document.body.classList.toggle("in-exam", total != null);
    $("#fill").style.width = total ? `${(100 * done) / total}%` : "0";
    $("#count").textContent = total && done < total ? `${done + 1} / ${total}` : "";
  },
  clock(label, seconds) {
    const c = $("#clock");
    c.classList.toggle("on", label != null);
    if (label == null) return;
    $("#clockLbl").textContent = label;
    $("#clockTime").textContent = seconds == null ? "··" : clockText(seconds);
    c.classList.toggle("low", seconds != null && seconds <= 10);
  },
  reset() {
    this.progress(0, null);
    this.clock(null);
    onEnter = null;
  },
};

// Enter presses the main button of the current screen.
let onEnter = null;
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || !onEnter || ["TEXTAREA", "SELECT", "BUTTON", "A"].includes(e.target.tagName)) return;
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
    ui.clock(label, left);
    if (left <= 0) stop();
  };
  const timer = setInterval(tick, 100);
  tick();
  done.skip = stop;
  return done;
}

// Show a button and resolve when the user clicks it or presses Enter.
function waitForButton(actions, note, id = "go") {
  return new Promise((resolve) => {
    ui.foot(actions, note);
    const go = () => { onEnter = null; resolve(); };
    $(`#${id}`).onclick = go;
    onEnter = go;
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
  async play(roundId, step) {
    const ok = await new Promise((resolve) => {
      const a = new Audio(`/api/audio/${roundId}/${step.id}.m4a`);
      a.onended = () => resolve(true);
      a.onerror = () => resolve(false);
      a.play().catch(() => resolve(false));
    });
    if (!ok) await this.speak(step.listen);
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

function textBox(placeholder) {
  return `<textarea id="box" spellcheck="false" autocorrect="off" autocapitalize="off" autocomplete="off" placeholder="${placeholder}"></textarea>`;
}

function promptBlock(step) {
  const bullets = step.bullets.length ? `<ul>${step.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : "";
  return `<div class="prompt">${esc(step.prompt)}${bullets}</div>`;
}

function micPanel() {
  return `<div class="mic" id="mic"><div class="state" id="micState"></div><canvas class="meter" id="meter"></canvas></div>`;
}

function writeScreen(step, previous) {
  const title = `<h2>${screenTitle(step)}</h2>`;
  if (step.photo) {
    return `${title}<div class="grid2"><img class="photo" src="${esc(step.photo)}" alt="">${textBox("Type your response here")}</div>`;
  }
  if (step.type === "summarize_conversation") {
    return `${title}${textBox("Type your response here")}`;
  }
  const prev = previous == null ? "" : `<div class="prev">${esc(previous) || "(empty)"}</div>`;
  return `${title}${promptBlock(step)}${prev}${textBox("Type your response here")}`;
}

function speakScreen(step) {
  const title = `<h2>${screenTitle(step)}</h2>`;
  if (step.photo) {
    return `${title}<div class="grid2"><img class="photo" src="${esc(step.photo)}" alt="">${micPanel()}</div>`;
  }
  return `${title}${promptBlock(step)}${micPanel()}`;
}

function listenScreen(step) {
  const title = step.type === "interactive_speaking" ? screenTitle(step) : "Listen to the conversation.";
  const mic = step.type === "interactive_speaking" ? micPanel() : "";
  return `<h2>${title}</h2><div class="speaker"><div class="play talking" id="play">${ICON.speaker}</div></div>${mic}`;
}

function introScreen(group) {
  const step = group[0], writes = step.skill === "writing";
  const listens = step.type === "summarize_conversation" || step.type === "interactive_speaking";
  let answer = shortDuration(step.answer);
  if (step.type === "interactive_writing") answer = group.map((s) => shortDuration(s.answer)).join(" + ");
  if (step.type === "interactive_speaking") answer = `${step.answer} s × ${group.length}`;
  const chip = (k, v) => `<div class="chip"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  return `<div class="icon-big">${ICON[TASK_ICON[step.type]]}</div><h1>${esc(step.name)}</h1>
    <div class="chips">${listens ? chip("Listen", "once") : chip("Prepare", step.prep ? `${step.prep} s` : "none")}${chip(writes ? "Write" : "Speak", answer)}</div>`;
}

// ---------- the exam ----------

let activeExam = null;
window.addEventListener("beforeunload", (e) => {
  if (activeExam) e.preventDefault();
});

class Exam {
  constructor(round) {
    this.round = round;
    this.steps = round.steps;
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
    ui.exam(`<h1>${esc(this.round.title)}</h1>
      <p class="muted">${plural(this.steps.length, "question")} · ${this.round.minutes} min</p>
      <div class="mic" style="margin:28px 0 18px">
        <div class="state" id="micState">${ICON.mic.replace("<svg", '<svg width="28" height="28"')}</div>
        <canvas class="meter" id="meter"></canvas>
        <div id="micHint"></div>
      </div>
      <details class="adv"><summary>Start from a later task</summary>
        <p style="margin-top:12px"><select id="from">${tasks.map(([s, i]) => `<option value="${i}">${i + 1}. ${esc(s.name)}</option>`).join("")}</select></p>
      </details>`);
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
    this.attemptId = (await api.post("/api/attempts", { round: this.round.id })).id;
    for (let i = from; i < this.steps.length; i++) {
      const step = this.steps[i];
      ui.progress(i, this.steps.length);
      if (i === from || step.type !== this.steps[i - 1].type) {
        ui.clock(null);
        ui.exam(introScreen(this.group(i)));
        await waitForButton(`<button class="btn" id="go">Start</button>`);
      }
      await (step.skill === "writing" ? this.write(step) : this.speak(step));
    }
    await api.post(`/api/attempts/${this.attemptId}/finish`);
    activeExam = null;
    Mic.close();
    this.finished();
  }

  async listen(step) {
    ui.clock("Listen");
    ui.foot(`<button class="btn" disabled>Listening</button>`);
    await Voice.play(this.round.id, step);
    $("#play").classList.replace("talking", "done");
  }

  async write(step) {
    if (step.type === "summarize_conversation") {
      ui.exam(listenScreen(step));
      await this.listen(step);
    }
    ui.exam(writeScreen(step, step.show_previous ? this.answers[step.show_previous] ?? "" : null), !!step.photo);
    const box = $("#box");
    if (step.prep) {
      box.disabled = true;
      const prep = countdown(step.prep, "Prepare");
      ui.foot(`<button class="btn ghost" id="skip">Start writing</button>`);
      $("#skip").onclick = prep.skip;
      await prep;
    }
    box.disabled = false;
    box.focus();
    Mic.beep();
    const draft = setInterval(() => this.post(step, box.value, "text/plain", false).catch(() => {}), 5000);
    const answer = countdown(step.answer, "Write");
    ui.foot(`<button class="btn" id="skip">Submit</button>`);
    $("#skip").onclick = answer.skip;
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
      ui.exam(speakScreen(step), !!step.photo);
    }
    if (step.prep) {
      $("#micState").textContent = "Not recording yet";
      const prep = countdown(step.prep, "Prepare");
      ui.foot(`<button class="btn" id="skip">Record now</button>`);
      $("#skip").onclick = prep.skip;
      await prep;
    }
    Mic.beep();
    $("#micState").innerHTML = `<span class="dot"></span> Recording`;
    $("#mic").classList.add("rec");
    const stopMeter = Mic.meter($("#meter"));
    const stop = Mic.record();
    const answer = countdown(step.answer, "Speak");
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
    ui.progress(this.steps.length, this.steps.length);
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
      </section>`).join("") || `<section class="box empty">No rounds found in rounds/.</section>`}
    </div>
    <div class="section-h">Your attempts</div>
    <section class="box">${attempts.map((a) => `
      <a class="row" href="#/attempt/${esc(a.id)}">
        <span class="grow"><span class="id">${esc(titles[a.round] || a.round)}</span><br><span class="muted">${when(a.started)} · ${plural(a.steps, "answer")}</span></span>
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

function resultsPage(d) {
  const { round, feedback: fb, manifest } = d;
  const answered = round.steps.filter((s) => manifest.steps[s.id]);
  const shown = round.steps.filter((s) => manifest.steps[s.id] || d.answers[s.id] != null);
  let head = `<h1>${esc(round.title)}</h1>
    <div class="muted">${when(manifest.started)} · ${plural(answered.length, "answer")} of ${round.steps.length}</div>`;
  if (fb) {
    const score = (k, label) => (fb.estimate?.[k] ? `<div class="score"><div class="k">${label}</div><div class="v">${bandRange(fb.estimate[k])}</div></div>` : "");
    head += `<div class="scores">${score("writing", "Writing estimate")}${score("speaking", "Speaking estimate")}</div>
      <p class="disclaimer">Estimated by ${esc(fb.grader)} from the official scoring guide. These are not official scores.</p>
      <p style="margin-top:16px">${esc(fb.summary)}</p>
      <h3 style="margin-top:22px">Top priorities</h3>
      <ol class="steps">${fb.priorities.map((p) => `<li><span><b>${esc(p.title)}.</b> ${esc(p.detail)}</span></li>`).join("")}</ol>`;
  }
  const waiting = fb ? "" : d.status === "in_progress"
    ? `<section class="box waiting"><h3>This attempt is not finished</h3>
        <p>You can still get feedback on the saved answers. Ask your coding agent: <b>“Grade det-coach attempt ${esc(manifest.id)}.”</b></p></section>`
    : `<section class="box waiting"><h3>Waiting for feedback</h3>
        <p>Ask your coding agent in this project folder: <b>“Grade my latest det-coach attempt.”</b></p>
        <p class="muted">The agent runs <code>det-coach packet ${esc(manifest.id)}</code>, grades each answer and writes <code>feedback.json</code>. This page updates by itself.</p></section>`;
  const steps = shown.map((s) => {
    const f = fb?.steps?.[s.id];
    return `<section class="box step" id="step-${esc(s.id)}">
      <div class="step-h"><h3>${esc(s.name)}${s.part ? ` <span class="muted">· ${esc(s.part)}</span>` : ""}</h3>${f ? `<span class="band">${bandRange(f.band)}</span>` : ""}</div>
      ${stepContext(round, s)}${stepAnswer(d, s)}${stepFeedback(f, s)}</section>`;
  }).join("");
  return `<section class="res-head">${head}</section>${waiting}${steps}`;
}

async function showAttempt(id, token) {
  ui.reset();
  let d = await api.get(`/api/attempts/${id}`);
  ui.page(resultsPage(d));
  // Wait for the grader: refresh once feedback.json appears.
  while (d.status !== "graded" && token === routeToken) {
    await sleep(4000);
    if (token !== routeToken) return;
    const next = await api.get(`/api/attempts/${id}`).catch(() => d);
    if (next.status !== d.status) ui.page(resultsPage(next));
    d = next;
  }
}

// ---------- preview: one exam screen, frozen, for screenshots and round authors ----------

async function showPreview(roundId, stepId) {
  ui.reset();
  const round = await api.get(`/api/rounds/${roundId}`);
  const i = round.steps.findIndex((s) => s.id === stepId);
  if (i < 0) throw new Error(`No step ${stepId} in ${roundId}`);
  const step = round.steps[i];
  ui.progress(i, round.steps.length);
  if (step.type === "interactive_speaking") ui.exam(listenScreen(step));
  else if (step.skill === "speaking") ui.exam(speakScreen(step), !!step.photo);
  else ui.exam(writeScreen(step, step.show_previous ? "(your answer to part 1)" : null), !!step.photo);
  ui.clock(step.skill === "writing" ? "Write" : "Speak", step.answer);
  ui.foot(`<button class="btn">${step.skill === "writing" ? "Submit" : "Record now"}</button>`, "");
}

// ---------- router ----------

let routeToken = 0;

async function route() {
  const token = ++routeToken;
  const [, view, a, b] = location.hash.replace(/^#\/?/, "/").split("/").map(decodeURIComponent);
  try {
    if (view === "exam" && a) await new Exam(await api.get(`/api/rounds/${a}`)).run();
    else if (view === "attempt" && a) await showAttempt(a, token);
    else if (view === "preview" && a && b) await showPreview(a, b);
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
