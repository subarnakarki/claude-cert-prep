// Progressive enhancement: without JS the page is a readable list of every card.
// With JS, show one card at a time with flip, prev/next and shuffle.
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
  let order = cards.map((_, i) => i);
  let index = 0;
  let flipped = false;

  function render() {
    const card = cards[order[index]];
    face.className = "face " + (flipped ? "face-back" : "face-front");
    face.innerHTML = flipped ? card.back : card.front;
    side.textContent = flipped ? "back" : "front";
    pos.textContent = `${card.tag}  ${index + 1}/${cards.length}`;
    stage.setAttribute("aria-pressed", String(flipped));
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

  list.hidden = true;
  deck.hidden = false;
  render();
})();
