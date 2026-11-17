// Static-site mode (the GitHub Pages build). There is no server, so this file does what
// study/progress.py and study/practice.py do in the Django app: readiness math,
// practice runs and exact-match grading. Progress is kept in localStorage.
//
// Question, choice and explanation HTML in content.json is produced at build time by
// the `codeify` filter (escaped first, then <code>-wrapped), so it is safe to insert.
(() => {
  "use strict";

  const body = document.body;
  if (!body.dataset.static) return;

  const BASE = body.dataset.base;
  const PAGE = body.dataset.page;
  const KEY = "ccarf-prep:v1";
  const PASS_LINE = 72;
  const WARN_LINE = 50;
  const READY_LINE = 85;
  const BAR_WIDTH = 16;
  const LETTERS = "abcdefghij";
  const MODES = { all: "All questions", missed: "Missed only", unanswered: "Unanswered only" };

  // -- storage ------------------------------------------------------------------------

  function load() {
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(KEY)) || {};
    } catch (_) {
      saved = {};
    }
    return {
      latest: saved.latest || {}, // question id → was the latest answer correct?
      attempts: saved.attempts || 0,
      runs: saved.runs || 0,
      run: saved.run || null,
    };
  }

  function save(state) {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch (_) {
      // Private mode or storage full: the session still works until the tab closes.
    }
  }

  let contentPromise = null;
  function content() {
    contentPromise =
      contentPromise ||
      fetch(BASE + "content.json")
        .then((response) => response.json())
        .then((data) => {
          data.byId = new Map(data.questions.map((q) => [q.id, q]));
          data.domainBySlug = new Map(data.domains.map((d) => [d.slug, d]));
          return data;
        });
    return contentPromise;
  }

  // -- readiness (mirrors study/progress.py) --------------------------------------------

  const statusFor = (ratio) =>
    ratio * 100 >= PASS_LINE ? "ok" : ratio * 100 >= WARN_LINE ? "warn" : "err";
  const cssFor = (status) => ({ ok: "ok", warn: "wa", err: "er" })[status];

  function textBar(ratio, width = BAR_WIDTH) {
    const filled = Math.min(width, Math.max(0, Math.floor(ratio * width + 0.5)));
    return "█".repeat(filled) + "░".repeat(width - filled);
  }

  function readiness(data, latest) {
    return data.domains.map((domain) => {
      const questions = data.questions.filter((q) => q.domain === domain.slug);
      const mastered = questions.filter((q) => latest[q.id] === true).length;
      const total = questions.length;
      const ratio = total ? mastered / total : 0;
      return { domain, mastered, total, ratio, percent: Math.floor(ratio * 100), status: statusFor(ratio) };
    });
  }

  function projectedScore(rows) {
    const weight = rows.reduce((sum, r) => sum + r.domain.weight, 0);
    return weight ? (rows.reduce((sum, r) => sum + r.domain.weight * r.ratio, 0) * 100) / weight : 0;
  }

  const weakest = (rows) =>
    rows
      .slice()
      .sort((a, b) => a.ratio - b.ratio || b.domain.weight - a.domain.weight || a.domain.number - b.domain.number)[0];

  const stopReason = (rows) =>
    rows.length && rows.every((r) => r.ratio * 100 >= READY_LINE) ? "end_turn" : "tool_use";

  function setStatus(el, status) {
    el.classList.remove("ok", "wa", "er");
    el.classList.add(cssFor(status));
  }

  // -- practice runs (mirrors study/practice.py) ----------------------------------------

  function shuffle(items) {
    for (let i = items.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [items[i], items[j]] = [items[j], items[i]];
    }
    return items;
  }

  function selectPool(data, state, domain, mode) {
    let questions = data.questions.filter((q) => !domain || q.domain === domain);
    if (mode === "missed") questions = questions.filter((q) => state.latest[q.id] === false);
    if (mode === "unanswered") questions = questions.filter((q) => !(q.id in state.latest));
    return questions.map((q) => q.id);
  }

  function emptyPoolMessage(mode) {
    if (mode === "missed") return "Nothing to retry: you haven't missed any questions here yet.";
    if (mode === "unanswered") return "You've answered every question here. Try all questions or only misses.";
    return "There are no questions for that domain yet.";
  }

  function startRun(data, state, ids, domain, mode) {
    const order = shuffle(ids.slice());
    const choiceOrder = {};
    for (const id of order) choiceOrder[id] = shuffle(data.byId.get(id).choices.map((c) => c.id));
    state.run = { question_ids: order, choice_order: choiceOrder, domain, mode, pos: 0, answers: {} };
    state.runs += 1;
    save(state);
    const url = BASE + "practice/run/";
    if (PAGE === "practice_run") {
      history.replaceState(null, "", url);
      window.dispatchEvent(new Event("ccarf:run"));
    } else {
      location.href = url;
    }
  }

  const sameSet = (a, b) => a.length === b.length && a.every((x) => b.includes(x));

  // -- pages ----------------------------------------------------------------------------

  function renderOverview(data, state) {
    const rows = readiness(data, state.latest);
    const weak = weakest(rows);
    const stop = stopReason(rows);
    const projected = projectedScore(rows);
    const mastered = rows.reduce((sum, r) => sum + r.mastered, 0);
    const total = rows.reduce((sum, r) => sum + r.total, 0);
    const lines = rows.map(
      (r) =>
        `  <a href="${BASE}domains/${r.domain.slug}/" class="p">${r.domain.slug.padEnd(12)}</a>` +
        `  ${String(r.domain.weight).padStart(3)}%  <span class="${cssFor(r.status)}" aria-hidden="true">` +
        `<span class="lg">${textBar(r.ratio)}</span><span class="sm">${textBar(r.ratio, 10)}</span></span>` +
        `<span class="sr-only">${r.percent}% ready</span>  ${String(r.mastered).padStart(2)}/${r.total}`,
    );
    const projectedCss = projected >= PASS_LINE ? "ok" : projected >= WARN_LINE ? "wa" : "er";
    const next = stop === "end_turn" ? "book the exam" : `practice ${weak.domain.slug}`;
    document.getElementById("status").innerHTML =
      `<span class="d">$</span> ccarf status\n\n${lines.join("\n")}\n\n` +
      `  <span class="d">mastered</span> ${mastered}/${total}   <span class="d">projected</span> ` +
      `<span class="${projectedCss}">${Math.round(projected)}%</span><span class="brk">   </span>` +
      `<span class="d">pass line ≈ ${PASS_LINE}%</span>\n` +
      `  <span class="d">stop_reason</span> <span class="p">"${stop}"</span><span class="brk">  </span>` +
      `<span class="d">next:</span> ${next}`;

    document.querySelectorAll("[data-runs]").forEach((el) => (el.textContent = state.runs));
    const start = document.querySelector("button[data-start]");
    if (start) {
      start.dataset.start = weak.domain.slug;
      start.textContent = `ccarf practice --domain ${weak.domain.slug}`;
    }
    const notes = document.querySelector("[data-notes]");
    if (notes) notes.href = `${BASE}domains/${weak.domain.slug}/`;

    if (new URLSearchParams(location.search).has("reset")) {
      const flash = document.createElement("p");
      flash.className = "flash";
      flash.setAttribute("role", "status");
      flash.textContent = "Progress reset. Every domain starts from zero.";
      document.getElementById("content").prepend(flash);
      history.replaceState(null, "", BASE);
    }
  }

  function renderWidgets(data, state) {
    const rows = new Map(readiness(data, state.latest).map((r) => [r.domain.slug, r]));
    document.querySelectorAll("[data-ready]").forEach((el) => {
      const row = rows.get(el.dataset.ready);
      if (!row) return;
      const fmt = el.dataset.fmt;
      if (fmt === "bar") {
        el.textContent = textBar(row.ratio);
        setStatus(el, row.status);
      } else if (fmt === "count") {
        el.textContent = `${row.mastered}/${row.total}`;
        if ("color" in el.dataset) setStatus(el, row.status);
      } else if (fmt === "of") {
        el.textContent = `${row.mastered} of ${row.total}`;
      }
    });
  }

  function bindStartButtons(data, state) {
    document.querySelectorAll("button[data-start]").forEach((button) => {
      button.addEventListener("click", () => {
        const domain = button.dataset.start;
        startRun(data, state, selectPool(data, state, domain, "all"), domain, "all");
      });
    });
  }

  function initSetup(data, state) {
    const form = document.querySelector("form[data-setup]");
    if (!form) return;
    const params = new URLSearchParams(location.search);
    if (data.domainBySlug.has(params.get("domain"))) form.elements.domain.value = params.get("domain");
    if (params.get("mode") in MODES) form.elements.mode.value = params.get("mode");

    const run = state.run;
    const resume = form.querySelector("[data-resume]");
    if (resume && run && run.pos < run.question_ids.length) {
      resume.textContent = `Resume run · ${Object.keys(run.answers).length}/${run.question_ids.length}`;
      resume.hidden = false;
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const domain = form.elements.domain.value;
      const mode = form.elements.mode.value || "all";
      const ids = selectPool(data, state, domain, mode);
      const error = form.querySelector("[data-setup-error]");
      if (!ids.length) {
        error.textContent = emptyPoolMessage(mode);
        error.hidden = false;
        return;
      }
      startRun(data, state, ids, domain, mode);
    });
  }

  function initReset(state) {
    const attempts = document.querySelector("[data-attempts]");
    if (attempts) attempts.textContent = `${state.attempts} answer${state.attempts === 1 ? "" : "s"}`;
    const button = document.querySelector("[data-reset]");
    if (!button) return;
    button.addEventListener("click", () => {
      try {
        localStorage.removeItem(KEY);
      } catch (_) {
        // nothing stored
      }
      location.href = BASE + "?reset=1";
    });
  }

  // -- the practice run page ------------------------------------------------------------

  function initRun(data) {
    const root = document.getElementById("run");
    const aside = document.getElementById("run-aside");

    function current() {
      const state = load();
      if (state.run) state.run.question_ids = state.run.question_ids.filter((id) => data.byId.has(id));
      return state;
    }

    function orderedChoices(run, question) {
      const order = run.choice_order[question.id] || [];
      const byId = new Map(question.choices.map((c) => [c.id, c]));
      const ordered = order.filter((id) => byId.has(id)).map((id) => byId.get(id));
      return ordered.concat(question.choices.filter((c) => !order.includes(c.id)));
    }

    function stats(run) {
      const answers = Object.values(run.answers);
      return { answered: answers.length, correct: answers.filter((a) => a.correct).length };
    }

    function renderAside(run) {
      const { answered, correct } = stats(run);
      const domain = data.domainBySlug.get(run.domain);
      aside.innerHTML =
        `<h2>This session</h2><dl><dt>Answered</dt><dd>${answered} of ${run.question_ids.length}</dd>` +
        `<dt>Correct</dt><dd>${correct}</dd><dt>Domains</dt><dd>${domain ? domain.short_name : "All"}</dd>` +
        `<dt>Mode</dt><dd>${MODES[run.mode] || MODES.all}</dd></dl>`;
    }

    function marks(run) {
      return run.question_ids
        .map((id, i) => {
          const answer = run.answers[id];
          if (answer) return answer.correct ? '<span class="mk-ok">●</span>' : '<span class="er">●</span>';
          return i === run.pos ? '<span class="p">◉</span>' : "○";
        })
        .join("");
    }

    function renderQuestion(state) {
      const run = state.run;
      const question = data.byId.get(run.question_ids[run.pos]);
      const answer = run.answers[question.id];
      const choices = orderedChoices(run, question);
      const correctIds = question.choices.filter((c) => c.correct).map((c) => c.id);
      const multi = correctIds.length > 1;
      const n = run.pos + 1;
      const total = run.question_ids.length;
      const { correct } = stats(run);
      document.title = `Question ${n} of ${total} · CCAR-F Prep`;

      const options = choices
        .map((choice, i) => {
          let outcome = "";
          let note = "";
          const checked = answer && answer.selected.includes(choice.id);
          if (answer && choice.correct) {
            outcome = "right";
            note = '<span class="sr-only"> (correct answer)</span>';
          } else if (checked) {
            outcome = "wrong";
            note = '<span class="sr-only"> (your pick, incorrect)</span>';
          }
          return (
            `<label class="opt ${outcome}"><input type="${multi ? "checkbox" : "radio"}" name="choice" ` +
            `value="${choice.id}"${checked ? " checked" : ""}${answer ? " disabled" : ""}>` +
            `<span class="k" aria-hidden="true">[${LETTERS[i]}]</span><span>${choice.html}${note}</span></label>`
          );
        })
        .join("");

      let html =
        `<div class="prog" aria-label="Question ${n} of ${total}, ${correct} correct so far">` +
        `<span class="marks" aria-hidden="true">${marks(run)}</span>` +
        `<span class="count" aria-hidden="true">${n}/${total}</span></div>` +
        `<div class="msg"><div class="role"><span>question ${n}</span>` +
        `<span class="p">domain: ${question.domain}</span></div>` +
        `<p class="qp" id="prompt">${question.prompt}</p></div>` +
        `<form id="answer">` +
        (multi && !answer ? `<p class="hint" id="hint">Select ${correctIds.length}</p>` : "") +
        `<fieldset class="opts" aria-labelledby="prompt"${multi && !answer ? ' aria-describedby="hint"' : ""}>` +
        `${options}</fieldset><p class="form-error" role="alert" hidden></p>` +
        (answer
          ? ""
          : `<div class="cta"><button class="btn pr" type="submit">Check answer</button>` +
            `<a class="btn" href="#results">End session</a></div>`) +
        `</form>`;

      if (answer) {
        const letterOf = (id) => `[${LETTERS[choices.findIndex((c) => c.id === id)]}]`;
        const chosen = choices.filter((c) => answer.selected.includes(c.id)).map((c) => letterOf(c.id));
        const right = choices.filter((c) => c.correct).map((c) => letterOf(c.id));
        const verdict = answer.correct
          ? '<span class="ok">✓ correct</span>'
          : '<span class="er">✗ incorrect</span>';
        html +=
          `<div class="result" tabindex="-1"><div class="bar">${verdict}` +
          `<span>you chose ${chosen.join("")}</span><span>answer ${right.join("")}</span></div>` +
          `<p>${question.explanation}</p></div>` +
          `<div class="cta"><button class="btn pr" type="button" data-next>` +
          `${run.pos === total - 1 ? "See results" : "Next question"}</button>` +
          `<a class="btn" href="#results">End session</a></div>`;
      }
      root.innerHTML = html;

      const form = root.querySelector("#answer");
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const selected = [...form.querySelectorAll("input[name=choice]:checked")].map((i) => Number(i.value));
        if (!selected.length) {
          const error = form.querySelector(".form-error");
          error.textContent = "Pick an answer first.";
          error.hidden = false;
          return;
        }
        const fresh = current();
        if (fresh.run.answers[question.id]) return render(); // already graded in another tab
        const isCorrect = sameSet(selected, correctIds);
        fresh.run.answers[question.id] = { selected: selected.sort((a, b) => a - b), correct: isCorrect };
        fresh.latest[question.id] = isCorrect;
        fresh.attempts += 1;
        save(fresh);
        render();
        const result = root.querySelector(".result");
        if (result) result.focus({ preventScroll: true });
      });

      const next = root.querySelector("[data-next]");
      if (next) {
        next.addEventListener("click", () => {
          const fresh = current();
          if (fresh.run.answers[fresh.run.question_ids[fresh.run.pos]]) fresh.run.pos += 1;
          save(fresh);
          if (fresh.run.pos >= fresh.run.question_ids.length) location.hash = "results";
          else render();
          window.scrollTo(0, 0);
        });
      }
    }

    function renderResults(state) {
      const run = state.run;
      const { answered, correct } = stats(run);
      const byDomain = new Map();
      for (const id of run.question_ids) {
        const answer = run.answers[id];
        if (!answer) continue;
        const slug = data.byId.get(id).domain;
        const entry = byDomain.get(slug) || { answered: 0, correct: 0 };
        entry.answered += 1;
        entry.correct += answer.correct ? 1 : 0;
        byDomain.set(slug, entry);
      }
      const rows = data.domains
        .filter((d) => byDomain.has(d.slug))
        .map((d) => {
          const { answered: a, correct: c } = byDomain.get(d.slug);
          const ratio = c / a;
          return (
            `  <span class="p">${d.slug.padEnd(12)}</span>  <span class="${cssFor(statusFor(ratio))}" aria-hidden="true">` +
            `<span class="lg">${textBar(ratio)}</span><span class="sm">${textBar(ratio, 10)}</span></span>` +
            `  ${String(Math.floor(ratio * 100)).padStart(3)}%  ${String(c).padStart(2)}/${a}`
          );
        });
      const missed = run.question_ids.filter((id) => run.answers[id] && !run.answers[id].correct);
      const percent = answered ? Math.floor((correct / answered) * 100) : 0;
      document.title = "Results · CCAR-F Prep";

      root.innerHTML =
        `<div class="page-head"><h1>Session results</h1>` +
        `<p class="score">${percent}%<small>${correct} of ${answered} correct</small></p></div>` +
        (rows.length
          ? `<div class="term" role="region" aria-label="Score by domain"><div class="bar">` +
            `<span>score by domain</span><span>${answered} answered</span></div>` +
            `<pre><span class="d">$</span> ccarf results\n\n${rows.join("\n")}\n</pre></div>`
          : `<p class="lede">You ended the session before answering anything.</p>`) +
        `<div class="cta">` +
        (missed.length ? `<button class="btn pr" type="button" data-retry>Retry ${missed.length} missed</button>` : "") +
        `<a class="btn${missed.length ? "" : " pr"}" href="${BASE}">Back to overview</a>` +
        `<a class="btn" href="${BASE}practice/">New session</a></div>`;
      aside.innerHTML =
        `<h2>What next</h2><p>Misses are queued for the "only ones I missed" mode. ` +
        `A question counts as mastered once your latest answer to it is right.</p>`;

      const retry = root.querySelector("[data-retry]");
      if (retry) {
        retry.addEventListener("click", () => {
          const fresh = current();
          startRun(data, fresh, missed, run.domain, "missed");
        });
      }
    }

    function render() {
      const state = current();
      if (!state.run || !state.run.question_ids.length) {
        location.replace(BASE + "practice/");
        return;
      }
      const finished = state.run.pos >= state.run.question_ids.length;
      if (finished || location.hash === "#results") {
        renderResults(state);
      } else {
        renderQuestion(state);
        renderAside(state.run);
      }
    }

    window.addEventListener("hashchange", render);
    window.addEventListener("ccarf:run", render);
    render();
  }

  // -- boot -----------------------------------------------------------------------------

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register(BASE + "sw.js").catch(() => {});
  }
  if (navigator.storage && navigator.storage.persist) {
    navigator.storage.persist().catch(() => {});
  }

  content().then((data) => {
    const state = load();
    if (PAGE === "overview") renderOverview(data, state);
    renderWidgets(data, state);
    bindStartButtons(data, state);
    if (PAGE === "practice_setup") initSetup(data, state);
    if (PAGE === "practice_reset") initReset(state);
    if (PAGE === "practice_run") initRun(data);
    body.dataset.ready = "1"; // lets tests wait for hydration
  });
})();
