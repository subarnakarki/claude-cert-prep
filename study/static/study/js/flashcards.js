// Progressive enhancement: without JS the page is a readable list of every card.
// With JS, show one card at a time with flip, prev/next and shuffle. The current card
// and shuffle order are remembered per filter, so the deck reopens where you left off.
(() => {
  "use strict";

  const deck = document.getElementById("deck");
  const list = document.getElementById("cards");
  if (!deck || !list) return;

  const cards = [...list.querySelectorAll(".card")]
    .filter((li) => li.querySelector(".front"))
    .map((li) => ({
      tag: li.querySelector(".tagline").textContent,
      front: li.querySelector(".front").innerHTML,
      back: li.querySelector(".back").innerHTML,
    }));
  if (cards.length === 0) return;

  const stage = deck.querySelector(".stage");
  const face = deck.querySelector(".face");
  const side = deck.querySelector(".side");
  const pos = deck.querySelector(".pos");
  const KEY = "ccarf-prep:flashcards";
  const deckId = new URLSearchParams(location.search).get("domain") || "all";
  let order = cards.map((_, i) => i);
  let index = 0;
  let flipped = false;

  function readAll() {
    try {
      return JSON.parse(localStorage.getItem(KEY)) || {};
    } catch (_) {
      return {};
    }
  }

  function remember() {
    const all = readAll();
    all[deckId] = { order, index, count: cards.length };
    try {
      localStorage.setItem(KEY, JSON.stringify(all));
    } catch (_) {
      // Private mode or storage full: position just isn't kept.
    }
  }

  function restore() {
    const saved = readAll()[deckId];
    if (!saved || saved.count !== cards.length) return; // the deck changed: start over
    const valid =
      Array.isArray(saved.order) &&
      saved.order.length === cards.length &&
      [...saved.order].sort((a, b) => a - b).every((v, i) => v === i);
    if (valid) order = saved.order;
    if (Number.isInteger(saved.index) && saved.index >= 0 && saved.index < cards.length) index = saved.index;
  }

  function render() {
    const card = cards[order[index]];
    face.className = "face " + (flipped ? "face-back" : "face-front");
    face.innerHTML = flipped ? card.back : card.front;
    side.textContent = flipped ? "back" : "front";
    pos.textContent = `${card.tag}  ${index + 1}/${cards.length}`;
    stage.setAttribute("aria-pressed", String(flipped));
    remember();
  }

  function animate() {
    stage.classList.remove("flipping");
    void stage.offsetWidth; // restart the animation
    stage.classList.add("flipping");
  }

  function flip() {
    flipped = !flipped;
    animate();
    render();
  }

  function go(step) {
    index = (index + step + cards.length) % cards.length;
    flipped = false;
    render();
  }

  function shuffle() {
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }
    index = 0;
    flipped = false;
    render();
  }

  const actions = { flip, prev: () => go(-1), next: () => go(1), shuffle };
  stage.addEventListener("click", flip);
  deck.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => actions[button.dataset.action]());
  });
  document.addEventListener("keydown", (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target.closest("input, select, textarea")) return;
    if (event.key === "ArrowLeft") go(-1);
    else if (event.key === "ArrowRight") go(1);
  });

  restore();
  list.hidden = true;
  deck.hidden = false;
  render();
})();
