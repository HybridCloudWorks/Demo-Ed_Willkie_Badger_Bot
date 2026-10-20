// Willkie Badger AI - chat page logic.
// Sends questions to /api/chat, shows answers, and adds voice features that
// fail softly: if the microphone or Read Aloud is unavailable, typing and
// reading still work.

(function () {
  "use strict";

  const chat = document.getElementById("chat");
  const form = document.getElementById("composer");
  const input = document.getElementById("question");
  const sendBtn = document.getElementById("send");
  const micBtn = document.getElementById("mic");
  const readBtn = document.getElementById("read-aloud");
  const autoVoice = document.getElementById("auto-voice");
  const autoVoiceState = document.getElementById("auto-voice-state");
  const statusEl = document.getElementById("status");

  const welcome = document.getElementById("welcome");

  let sessionId = null;          // kept in memory only; nothing is stored
  let cloudTts = false;          // set from /api/health
  let currentAudio = null;       // playing <audio> element (Cloud TTS)
  let lastReply = chat.querySelector(".bubble.bot .text").textContent; // greeting
  let questionCount = 0;
  const AUTO_VOICE_KEY = "badger-auto-voice";   // presenter preference only

  // What the "thinking" bubble says while we wait. Mirrors the real steps
  // the agent takes, so students connect the wait with the plan.
  const THINKING_STEPS = [
    "💬 Reading your question…",
    "📚 Opening the school library…",
    "🧠 Asking Gemini to write the answer…",
  ];

  // ---------- helpers ----------
  function addBubble(text, who, extraClass) {
    const bubble = document.createElement("div");
    bubble.className = "bubble " + who + (extraClass ? " " + extraClass : "");
    const body = document.createElement("div");
    body.className = "text";
    body.textContent = text;
    bubble.appendChild(body);
    chat.appendChild(bubble);
    chat.scrollTop = chat.scrollHeight;
    return bubble;
  }

  // "How I answered": a small fold-out under each answer listing the steps
  // the agent really took (library lookup, pages found, Gemini). This is the
  // Cloud Architect "behind the scenes" moment.
  function addSteps(bubble, steps) {
    if (!steps || !steps.length) return;
    const details = document.createElement("details");
    details.className = "how";
    const summary = document.createElement("summary");
    summary.textContent = "🔍 How I answered (" + steps.length + " steps)";
    details.appendChild(summary);
    const list = document.createElement("ol");
    steps.forEach(function (s) {
      const li = document.createElement("li");
      const icon = document.createElement("span");
      icon.className = "how-icon";
      icon.textContent = s.icon || "•";
      const title = document.createElement("strong");
      title.textContent = s.title || "";
      li.appendChild(icon);
      li.appendChild(title);
      if (s.detail) {
        const detail = document.createElement("span");
        detail.className = "how-detail";
        detail.textContent = s.detail;
        li.appendChild(detail);
      }
      list.appendChild(li);
    });
    details.appendChild(list);
    details.addEventListener("toggle", function () { chat.scrollTop = chat.scrollHeight; });
    bubble.appendChild(details);
    chat.scrollTop = chat.scrollHeight;
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    input.disabled = busy;
    if (!busy) input.focus();
  }

  // ---------- chat ----------
  async function ask(question) {
    const q = (question || "").trim();
    if (!q) return;
    stopAudio();
    if (welcome) welcome.classList.add("hidden");   // make room for the conversation
    addBubble(q, "student");
    input.value = "";
    setBusy(true);
    const typing = addBubble(THINKING_STEPS[0], "bot", "typing");
    let stepIndex = 0;
    const ticker = setInterval(function () {
      stepIndex = Math.min(stepIndex + 1, THINKING_STEPS.length - 1);
      typing.querySelector(".text").textContent = THINKING_STEPS[stepIndex];
    }, 900);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, session_id: sessionId }),
      });
      const data = await res.json().catch(function () { return {}; });
      clearInterval(ticker);
      typing.remove();
      if (!res.ok) {
        addBubble(data.detail || "Something went wrong. Please try again.", "bot", "error");
        return;
      }
      sessionId = data.session_id;
      const bubble = addBubble(data.reply, "bot");
      addSteps(bubble, data.steps);
      lastReply = data.reply;
      questionCount += 1;
      updateStatus();
      if (autoVoice.checked) speak(lastReply);   // Auto voice is opt-in
    } catch (err) {
      clearInterval(ticker);
      typing.remove();
      addBubble("I can't reach the server right now. Is the app still running?", "bot", "error");
    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    ask(input.value);
  });

  // Chips: the visible label can differ from the question sent (data-q).
  document.querySelectorAll(".chip").forEach(function (chip) {
    chip.addEventListener("click", function () { ask(chip.dataset.q || chip.textContent); });
  });

  // ---------- Read Aloud (text-to-speech) ----------
  // One button next to the input reads the latest answer; it turns into Stop
  // while audio is playing. The Auto voice toggle plays each new answer.
  function markPlaying() {
    readBtn.classList.add("playing");
    readBtn.textContent = "⏹ Stop";
  }

  function markStopped() {
    readBtn.classList.remove("playing");
    readBtn.textContent = "🔊 Read Aloud";
  }

  function stopAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    markStopped();
  }

  function speakWithBrowser(text) {
    if (!("speechSynthesis" in window)) {
      readBtn.textContent = "Voice not available";
      readBtn.disabled = true;
      autoVoice.checked = false;
      autoVoice.disabled = true;
      return;
    }
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-US";
    utter.rate = 0.95;
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find(function (v) { return /en[-_]US/i.test(v.lang) && /Google|Natural|Online/i.test(v.name); })
      || voices.find(function (v) { return /en[-_]US/i.test(v.lang); });
    if (preferred) utter.voice = preferred;
    utter.onend = markStopped;
    utter.onerror = markStopped;
    window.speechSynthesis.cancel();
    markPlaying();
    window.speechSynthesis.speak(utter);
  }

  async function speak(text) {
    stopAudio();
    if (!text) return;
    if (cloudTts) {
      // Try Google Cloud Text-to-Speech first; fall back to the browser voice.
      try {
        const res = await fetch("/api/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: text }),
        });
        if (res.ok) {
          const blob = await res.blob();
          const audio = new Audio(URL.createObjectURL(blob));
          currentAudio = audio;
          audio.onended = markStopped;
          audio.onerror = markStopped;
          markPlaying();
          await audio.play();
          return;
        }
      } catch (err) {
        // ignore and fall back
      }
    }
    speakWithBrowser(text);
  }

  readBtn.addEventListener("click", function () {
    if (readBtn.classList.contains("playing")) {
      stopAudio();
    } else {
      speak(lastReply);
    }
  });

  function updateAutoVoiceLabel() {
    autoVoiceState.textContent = autoVoice.checked ? "on" : "off";
  }
  autoVoice.addEventListener("change", function () {
    updateAutoVoiceLabel();
    if (!autoVoice.checked) stopAudio();
    try { localStorage.setItem(AUTO_VOICE_KEY, autoVoice.checked ? "1" : "0"); } catch (e) { /* ignore */ }
  });
  try { autoVoice.checked = localStorage.getItem(AUTO_VOICE_KEY) === "1"; } catch (e) { /* ignore */ }
  updateAutoVoiceLabel();
  if (window.speechSynthesis) window.speechSynthesis.getVoices(); // warm up voice list

  // ---------- Microphone (speech-to-text), optional ----------
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Recognition) {
    micBtn.hidden = false;
    let recognizer = null;
    micBtn.addEventListener("click", function () {
      if (recognizer) {               // already listening -> stop
        recognizer.stop();
        return;
      }
      try {
        stopAudio();
        recognizer = new Recognition();
        recognizer.lang = "en-US";
        recognizer.interimResults = false;
        recognizer.maxAlternatives = 1;
        recognizer.onresult = function (event) {
          const text = event.results[0][0].transcript;
          input.value = text;           // show it so it can be fixed before sending
          input.focus();
        };
        recognizer.onerror = function () {
          input.placeholder = "Microphone didn't work. Please type your question.";
        };
        recognizer.onend = function () {
          recognizer = null;
          micBtn.classList.remove("listening");
          micBtn.textContent = "🎤 Ask";
        };
        micBtn.classList.add("listening");
        micBtn.textContent = "🎤 Listening…";
        recognizer.start();
      } catch (err) {
        recognizer = null;
        micBtn.hidden = true;        // hide the mic; typing still works
      }
    });
  }

  // ---------- startup ----------
  let health = null;
  function updateStatus() {
    if (!health) return;
    statusEl.textContent = "Model: " + health.model + " · Voice: " + (cloudTts ? "Google Cloud" : "browser") +
      " · Library: " + health.knowledge_pages + " pages" +
      (questionCount ? " · Questions: " + questionCount : "");
  }
  fetch("/api/health")
    .then(function (r) { return r.json(); })
    .then(function (h) {
      health = h;
      cloudTts = !!h.cloud_tts;
      updateStatus();
    })
    .catch(function () { statusEl.textContent = "Server not reachable"; });

  input.focus();
})();
