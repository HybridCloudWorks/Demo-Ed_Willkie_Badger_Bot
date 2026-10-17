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
  const stopAllBtn = document.getElementById("stop-all");
  const statusEl = document.getElementById("status");

  let sessionId = null;          // kept in memory only; nothing is stored
  let cloudTts = false;          // set from /api/health
  let currentAudio = null;       // playing <audio> element (Cloud TTS)
  let currentSpeakBtn = null;    // the Read Aloud button that is active

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

  function addReadAloud(bubble, text) {
    const actions = document.createElement("div");
    actions.className = "actions";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "speak";
    btn.textContent = "🔊 Read Aloud";
    btn.addEventListener("click", function () {
      if (btn.classList.contains("playing")) {
        stopAudio();
      } else {
        speak(text, btn);
      }
    });
    actions.appendChild(btn);
    bubble.appendChild(actions);
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
    addBubble(q, "student");
    input.value = "";
    setBusy(true);
    const typing = addBubble("Badger AI is thinking…", "bot", "typing");
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, session_id: sessionId }),
      });
      const data = await res.json().catch(function () { return {}; });
      typing.remove();
      if (!res.ok) {
        addBubble(data.detail || "Something went wrong. Please try again.", "bot", "error");
        return;
      }
      sessionId = data.session_id;
      const bubble = addBubble(data.reply, "bot");
      addReadAloud(bubble, data.reply);
    } catch (err) {
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

  document.querySelectorAll(".chip").forEach(function (chip) {
    chip.addEventListener("click", function () { ask(chip.textContent); });
  });

  // ---------- Read Aloud (text-to-speech) ----------
  function markPlaying(btn) {
    currentSpeakBtn = btn;
    btn.classList.add("playing");
    btn.textContent = "⏹ Stop";
    stopAllBtn.hidden = false;
  }

  function markStopped() {
    if (currentSpeakBtn) {
      currentSpeakBtn.classList.remove("playing");
      currentSpeakBtn.textContent = "🔊 Read Aloud";
      currentSpeakBtn = null;
    }
    stopAllBtn.hidden = true;
  }

  function stopAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    markStopped();
  }

  function speakWithBrowser(text, btn) {
    if (!("speechSynthesis" in window)) {
      btn.textContent = "Read Aloud not available here";
      btn.disabled = true;
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
    markPlaying(btn);
    window.speechSynthesis.speak(utter);
  }

  async function speak(text, btn) {
    stopAudio();
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
          markPlaying(btn);
          await audio.play();
          return;
        }
      } catch (err) {
        // ignore and fall back
      }
    }
    speakWithBrowser(text, btn);
  }

  stopAllBtn.addEventListener("click", stopAudio);
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
  fetch("/api/health")
    .then(function (r) { return r.json(); })
    .then(function (h) {
      cloudTts = !!h.cloud_tts;
      statusEl.textContent = "Model: " + h.model + " · Voice: " + (cloudTts ? "Google Cloud" : "browser") +
        " · Library: " + h.knowledge_pages + " pages";
    })
    .catch(function () { statusEl.textContent = "Server not reachable"; });

  input.focus();
})();
