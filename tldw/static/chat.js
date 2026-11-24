const workspace = document.querySelector("#workspace");
const readView = document.querySelector("#read-view");
const chat = document.querySelector("#chat");
const title = document.querySelector("#chat-title");
const form = document.querySelector("#chat-form");
const turns = document.querySelector("#chat-turns");
const question = document.querySelector("#chat-question");
const send = document.querySelector("#send-question");
const retry = document.querySelector("#retry-question");
const status = document.querySelector("#chat-status");
const spinner = document.querySelector("#chat-spinner");
const sidebar = document.querySelector("#chat-history");
const chatList = document.querySelector("#chat-list");
const openButton = readView.querySelector("[data-open-chat]");
const essay = readView.querySelector("article[data-video-id]")?.dataset;
const workingMessages = [
  "Skimming the transcript…",
  "Fast-forwarding past the sponsor read…",
  "Looking for the short version…",
  "Asking the speaker to get to the point…",
  "Untangling the microphones…",
  "Reticulating timestamps…",
  "Skipping the obligatory introductions…",
  "Checking who said that…",
  "Following a promising tangent…",
  "Finding the end of that tangent…",
  "Turning the playback speed up to read…",
  "Picking the footnotes out of the audio…",
  "Giving the rewind button a break…",
  "Reuniting a claim with its timestamp…",
  "Saving you the outro…",
];

function load(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem("tldw." + key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try {
    localStorage.setItem("tldw." + key, JSON.stringify(value));
  } catch {
    // The open document still has the conversation if storage is unavailable.
    // shortcut: chats are never deleted, so a full localStorage (about 5 MB) stops saving; add deletion then.
  }
}

const readStore = () => load("chats", { current: null, chats: [] });
const currentChat = () =>
  store.chats.find((chat) => chat.id === store.current) ??
  { id: String(Date.now()), title: "", updated: Date.now(), turns: [], draft: "", unanswered: false };

let store = readStore();
let thread = currentChat();
let request = null;
let readingY = 0;
let messageIndex = 0;

function saveThread() {
  // Another tab may have saved since this one loaded, so merge into the stored list.
  store = readStore();
  store.chats = [thread, ...store.chats.filter((chat) => chat.id !== thread.id && chat.turns.length)];
  store.current = thread.id;
  save("chats", store);
  showHistory();
}

function showHistory() {
  if (!chatList) return;
  const items = store.chats.toSorted((a, b) => b.updated - a.updated).map((chat) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const date = document.createElement("time");
    const updated = new Date(chat.updated);
    button.type = "button";
    button.dataset.chatId = chat.id;
    button.textContent = chat.title || "New chat";
    if (chat.id === thread.id) button.setAttribute("aria-current", "true");
    date.dateTime = updated.toISOString();
    date.textContent = updated.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    item.append(button, " ", date);
    return item;
  });
  chatList.replaceChildren(...items);
}

function openChat(id) {
  request?.abort();
  request = null;
  store = readStore();
  store.current = id;
  thread = currentChat();
  saveThread();
  loadThread();
  question.focus();
}

sidebar?.addEventListener("click", (event) => {
  const id = event.target.closest("[data-chat-id]")?.dataset.chatId;
  if (id || event.target.closest("#new-chat")) openChat(id);
});

function setPanel(open) {
  workspace.classList.toggle("panel-open", open);
  chat.hidden = !open;
  openButton.hidden = open;
  openButton.setAttribute("aria-expanded", String(open));
}

openButton.addEventListener("click", () => {
  readingY = window.scrollY;
  setPanel(true);
  scrollConversation();
  title.focus({ preventScroll: true });
});

document.querySelector("#close-chat").addEventListener("click", () => {
  // On narrow screens the panel replaces the page, which loses the scroll position.
  const wasReplaced = !readView.getClientRects().length;
  setPanel(false);
  if (wasReplaced) window.scrollTo(0, readingY);
  openButton.focus({ preventScroll: true });
});

function appendTurn(turn) {
  const item = document.createElement("li");
  const prompt = document.createElement("p");
  const answer = document.createElement("div");
  prompt.className = "chat-question";
  prompt.textContent = turn.question;
  answer.className = "chat-answer";
  if (turn.html) answer.innerHTML = turn.html;
  item.append(prompt, answer);
  turns.append(item);
  return answer;
}

function scrollConversation() {
  const log = turns.parentElement;
  log.scrollTop = log.scrollHeight;
}

function updateComposer() {
  question.value = thread.draft;
  question.readOnly = Boolean(request);
  send.disabled = Boolean(request);
  spinner.hidden = !request;
  retry.hidden = Boolean(request) || !thread.unanswered;
}

function loadThread() {
  turns.replaceChildren();
  for (const turn of thread.turns) appendTurn(turn);
  status.textContent = thread.unanswered ? "Question ready to retry." : "";
  updateComposer();
  showHistory();
  scrollConversation();
}

question.addEventListener("input", () => {
  thread.draft = question.value;
  thread.unanswered = false;
  retry.hidden = true;
  status.textContent = "";
  saveThread();
});

async function readReply(response, preview) {
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.error ?? "Couldn't answer right now. Try again.");
  }
  const log = turns.parentElement;
  let pending = "";
  for await (const chunk of response.body.pipeThrough(new TextDecoderStream())) {
    const lines = (pending + chunk).split("\n");
    pending = lines.pop();
    const atBottom = log.scrollHeight - log.clientHeight - log.scrollTop < 8;
    for (const line of lines) {
      const event = JSON.parse(line);
      if (event.error) throw new Error(event.error);
      if (typeof event.answer === "string" && typeof event.html === "string") return event;
      if (event.clear) preview.data = "";
      if (typeof event.delta === "string") preview.appendData(event.delta);
    }
    if (atBottom) scrollConversation();
  }
  throw new Error("Couldn't read the reply. Try again.");
}

function showWorkingMessage() {
  status.textContent = workingMessages[messageIndex];
  messageIndex = (messageIndex + 1) % workingMessages.length;
}

async function sendQuestion() {
  const text = question.value.trim();
  if (!text || request) return;
  const controller = new AbortController();
  request = controller;
  thread.title ||= text.slice(0, 80);
  thread.draft = text;
  thread.unanswered = true;
  saveThread();
  updateComposer();
  showWorkingMessage();
  const timer = window.setInterval(showWorkingMessage, 2000);
  const answer = appendTurn({ question: text });
  const preview = document.createTextNode("");
  answer.append(preview);
  answer.setAttribute("aria-busy", "true");
  scrollConversation();

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: text,
        // An essay's panel asks about that essay; every other page asks about everything.
        context: essay ? { mode: "essay", video_id: essay.videoId } : { mode: "all" },
        turns: thread.turns.map(({ question, answer }) => ({ question, answer })),
      }),
      signal: controller.signal,
    });
    const result = await readReply(response, preview);
    controller.signal.throwIfAborted();
    const turn = { question: text, answer: result.answer, html: result.html };
    thread.turns.push(turn);
    thread.draft = "";
    thread.unanswered = false;
    thread.updated = Date.now();
    saveThread();
    answer.innerHTML = result.html;
    answer.removeAttribute("aria-busy");
    status.textContent = "";
  } catch (error) {
    answer.parentElement?.remove();
    if (!controller.signal.aborted) {
      status.textContent = error instanceof TypeError ? "Couldn't connect. Try again." : error.message;
    }
  } finally {
    window.clearInterval(timer);
    if (request === controller) {
      if (controller.signal.aborted) status.textContent = "";
      request = null;
      updateComposer();
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void sendQuestion();
});

retry.addEventListener("click", () => void sendQuestion());

function updateViewport() {
  workspace.style.setProperty("--chat-viewport", window.visualViewport.height + "px");
}

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", updateViewport);
  updateViewport();
}

window.addEventListener("pagehide", () => request?.abort());

function reloadChats() {
  store = readStore();
  thread = currentChat();
  loadThread();
}

window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  request = null;
  reloadChats();
});
// Follow changes made in other tabs, except while a reply is streaming into this one.
window.addEventListener("storage", (event) => {
  if (event.key === "tldw.chats" && !request) reloadChats();
});

if (sidebar && matchMedia("(max-width: 750px)").matches) sidebar.open = false;

if (workspace.dataset.mode === "ask") document.querySelector("#back-to-read").href = load("readPath", "/");
else {
  save("readPath", location.pathname + location.search);
  setPanel(false);
}
loadThread();
