const workspace = document.querySelector("#workspace");
const readView = document.querySelector("#read-view");
const chat = document.querySelector("#chat");
const title = document.querySelector("#chat-title");
const form = document.querySelector("#chat-form");
const turns = document.querySelector("#chat-turns");
const scope = document.querySelector("#chat-scope");
const essayLabel = document.querySelector("#chat-essay");
const question = document.querySelector("#chat-question");
const send = document.querySelector("#send-question");
const retry = document.querySelector("#retry-question");
const status = document.querySelector("#chat-status");
const close = document.querySelector("#close-chat");
const expand = document.querySelector("#expand-chat");
const back = document.querySelector("#back-to-read");
const modeLinks = document.querySelectorAll(".site-modes a");
const askPath = "/ask";

function load(key, fallback) {
  try {
    return JSON.parse(sessionStorage.getItem("tldw." + key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try {
    sessionStorage.setItem("tldw." + key, JSON.stringify(value));
  } catch {
    // The open document still has the conversation if storage is unavailable.
  }
}

const emptyThread = () => ({ mode: null, essay: null, turns: [], draft: "", retryScope: null });
const currentPath = () => location.pathname + location.search;
const currentEssay = () => readView.querySelector("article[data-video-id]")?.dataset;
const readTarget = () => load("lastEssay", currentEssay() ? readPath : "/");

let thread = load("thread", emptyThread());
let mode = workspace.dataset.mode;
let readPath = mode === "read" ? currentPath() : null;
let readTitle = mode === "read" ? document.title : "TL;DW";
let panelOpen = false;
let request = null;
let navigation = 0;
let restoreFrame = 0;
let layoutWidth = window.innerWidth;

function rememberReading() {
  const essay = currentEssay();
  if (!essay || !readView.getClientRects().length || restoreFrame) return;
  const blocks = Array.from(readView.querySelector(".essay-body").children);
  const block = window.scrollY ? blocks.findIndex((item) => item.getBoundingClientRect().bottom > 0) : -1;
  const offset = block === -1 ? window.scrollY : -blocks[block].getBoundingClientRect().top;
  save("reading." + essay.videoId, { block, offset });
}

function restoreReading() {
  cancelAnimationFrame(restoreFrame);
  restoreFrame = requestAnimationFrame(() => {
    if (readView.getClientRects().length) {
      const essay = currentEssay();
      const position = essay && load("reading." + essay.videoId, null);
      const block = position && readView.querySelector(".essay-body").children[position.block];
      const top = block
        ? window.scrollY + block.getBoundingClientRect().top + Math.min(position.offset, block.offsetHeight - 1)
        : position?.offset ?? 0;
      window.scrollTo({ top, behavior: "instant" });
    }
    restoreFrame = requestAnimationFrame(() => { restoreFrame = 0; });
  });
}

function updateContext() {
  scope.value = thread.mode ?? "all";
  scope.options[1].disabled = !thread.essay;
  essayLabel.hidden = thread.mode !== "essay";
  essayLabel.textContent = thread.essay?.title ?? "";

  const essay = currentEssay();
  const openButton = readView.querySelector("[data-open-chat]");
  if (openButton) {
    openButton.hidden = panelOpen || !thread.mode;
    openButton.setAttribute("aria-expanded", String(panelOpen));
  }
  const canSwitch = essay && (thread.mode !== "essay" || thread.essay?.id !== essay.videoId);
  const essayButton = readView.querySelector("[data-ask-essay]");
  if (essayButton) essayButton.hidden = !canSwitch || panelOpen;
  chat.querySelector("[data-ask-essay]").hidden = !canSwitch || !panelOpen;
}

function updateView() {
  workspace.dataset.mode = mode;
  workspace.classList.toggle("panel-open", panelOpen);
  readView.hidden = mode === "ask";
  chat.hidden = mode === "read" && !panelOpen;
  close.hidden = expand.hidden = mode === "ask";
  back.hidden = mode === "read";
  back.href = readTarget();
  for (const link of modeLinks) {
    if (link.dataset.show === mode) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
    if (link.dataset.show === "read") link.href = mode === "ask" ? readTarget() : "/";
  }
  document.title = mode === "ask" ? "Ask · TL;DW" : readTitle;
  updateContext();
}

function focusReading() {
  const heading = readView.querySelector("h1") ?? document.querySelector(".site-modes [data-show='read']");
  heading.focus({ preventScroll: true });
}

function showAsk(push) {
  navigation++;
  if (mode === "ask") return;
  rememberReading();
  if (!thread.mode) {
    thread.mode = "all";
    save("thread", thread);
  }
  if (push) history.pushState(null, "", askPath);
  panelOpen = false;
  mode = "ask";
  updateView();
  window.scrollTo(0, 0);
  scrollConversation();
  title.focus({ preventScroll: true });
}

async function showRead(target, push) {
  const transition = ++navigation;
  if (target !== readPath) {
    try {
      let response = await fetch(target);
      if (response.status === 404 && target !== "/") {
        target = "/";
        response = await fetch(target);
      }
      if (!response.ok) throw new Error("Read page unavailable");
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      if (transition !== navigation) return;
      readView.replaceChildren(...page.getElementById("read-view").childNodes);
      readTitle = page.title;
      readPath = target;
      if (currentEssay()) save("lastEssay", target);
      else if (target === "/") save("lastEssay", "/");
    } catch {
      if (transition === navigation) {
        status.textContent = "Couldn't open Read. Try again.";
      }
      return;
    }
  }
  if (push) history.pushState(null, "", target);
  else if (currentPath() !== target) history.replaceState(null, "", target);
  panelOpen = false;
  mode = "read";
  updateView();
  restoreReading();
  focusReading();
}

function openPanel(useCurrentEssay) {
  rememberReading();
  if (useCurrentEssay) {
    const essay = currentEssay();
    thread.essay = { id: essay.videoId, title: essay.essayTitle };
    thread.mode = "essay";
    save("thread", thread);
  }
  panelOpen = true;
  updateView();
  if (readView.getClientRects().length) restoreReading();
  else window.scrollTo(0, 0);
  scrollConversation();
  title.focus({ preventScroll: true });
}

workspace.addEventListener("click", (event) => {
  if (event.target.closest("[data-ask-essay]")) openPanel(true);
  else if (event.target.closest("[data-open-chat]")) openPanel(false);
});

close.addEventListener("click", () => {
  rememberReading();
  panelOpen = false;
  updateView();
  restoreReading();
  readView.querySelector("[data-open-chat]").focus({ preventScroll: true });
});

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-show]");
  if (!link || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  if (link.dataset.show === "read" && mode === "read") return;
  event.preventDefault();
  if (link.dataset.show === "ask") showAsk(true);
  else void showRead(readTarget(), true);
});

window.addEventListener("popstate", () => {
  if (location.pathname === askPath) showAsk(false);
  else void showRead(currentPath(), false);
});

scope.addEventListener("change", () => {
  thread.mode = scope.value;
  save("thread", thread);
  updateContext();
});

function appendTurn(turn) {
  const item = document.createElement("li");
  const prompt = document.createElement("p");
  const answer = document.createElement("div");
  prompt.className = "chat-question";
  prompt.textContent = turn.question;
  answer.className = "chat-answer";
  answer.innerHTML = turn.html;
  item.append(prompt, answer);
  turns.append(item);
}

function scrollConversation() {
  const log = turns.parentElement;
  log.scrollTop = log.scrollHeight;
}

function updateComposer() {
  question.value = thread.draft;
  question.readOnly = Boolean(request);
  send.disabled = Boolean(request);
  retry.hidden = Boolean(request) || !thread.retryScope;
}

function loadThread() {
  if (mode === "ask" && !thread.mode) {
    thread.mode = "all";
    save("thread", thread);
  }
  turns.replaceChildren();
  for (const turn of thread.turns) appendTurn(turn);
  status.textContent = thread.retryScope ? "Question ready to retry." : "";
  updateView();
  updateComposer();
  scrollConversation();
}

question.addEventListener("input", () => {
  thread.draft = question.value;
  thread.retryScope = null;
  retry.hidden = true;
  status.textContent = "";
  save("thread", thread);
});

async function sendQuestion(context) {
  const text = question.value.trim();
  if (!text || request) return;
  const controller = new AbortController();
  request = controller;
  thread.draft = text;
  thread.retryScope = context;
  save("thread", thread);
  updateComposer();
  status.textContent = "Waiting for a reply…";

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: text,
        context,
        turns: thread.turns.map(({ question, answer }) => ({ question, answer })),
      }),
      signal: controller.signal,
    });
    const result = await response.json().catch(() => ({}));
    if (request !== controller || controller.signal.aborted) return;
    if (!response.ok) throw new Error(result.error ?? "Couldn't answer right now. Try again.");
    if (typeof result.answer !== "string" || typeof result.html !== "string") {
      throw new Error("Couldn't read the reply. Try again.");
    }
    const turn = { question: text, answer: result.answer, html: result.html };
    thread.turns.push(turn);
    thread.draft = "";
    thread.retryScope = null;
    save("thread", thread);
    appendTurn(turn);
    scrollConversation();
    status.textContent = "";
  } catch (error) {
    if (!controller.signal.aborted) {
      status.textContent = error instanceof TypeError ? "Couldn't connect. Try again." : error.message;
    }
  } finally {
    if (request === controller && !controller.signal.aborted) {
      request = null;
      updateComposer();
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const context = { mode: thread.mode ?? "all" };
  if (context.mode === "essay") context.video_id = thread.essay.id;
  void sendQuestion(context);
});

retry.addEventListener("click", () => void sendQuestion(thread.retryScope));

window.addEventListener("scroll", () => {
  if (layoutWidth === window.innerWidth) rememberReading();
}, { passive: true });
window.addEventListener("resize", () => {
  if (layoutWidth === window.innerWidth) return;
  layoutWidth = window.innerWidth;
  restoreReading();
  if (panelOpen && !readView.getClientRects().length) window.scrollTo(0, 0);
});

function updateViewport() {
  workspace.style.setProperty("--chat-viewport", window.visualViewport.height + "px");
}

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", updateViewport);
  updateViewport();
}

window.addEventListener("pagehide", () => {
  rememberReading();
  request?.abort();
});
window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  request = null;
  thread = load("thread", thread);
  if (mode === "read" && currentEssay()) save("lastEssay", readPath);
  loadThread();
  restoreReading();
});

history.scrollRestoration = "manual";
loadThread();
const essay = currentEssay();
if (mode === "read" && essay) {
  save("lastEssay", readPath);
  if (load("reading." + essay.videoId, null)) restoreReading();
}
