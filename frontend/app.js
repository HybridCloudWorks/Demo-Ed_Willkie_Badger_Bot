// Willkie Badger AI - chat page logic.
// Sends questions to /api/chat, shows answers with the steps the agent took,
// drives the animated mascot (one clip per state), and adds voice features
// that fail softly: if the mic or Read Aloud is unavailable, typing still works.

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
  const ASSET_V = document.body.dataset.v || "";

  let sessionId = null;          // kept in memory only; nothing is stored
  let cloudTts = false;          // set from /api/health
  let currentAudio = null;       // playing <audio> element (Cloud TTS)
  let lastReply = chat.querySelector(".bubble.bot .text").textContent; // greeting
  let questionCount = 0;
  const AUTO_VOICE_KEY = "badger-auto-voice";   // presenter preference only

  // ---------- mascot ----------
  // Each state is a short clip made with Google's Veo (scripts/generate_mascot_video.py).
  // "loop" clips repeat; the others play once and fall back to idle.
  const MASCOT = {
    wave:      { caption: "Hi, Badgers!",                 loop: false },
    idle:      { caption: "Ask me anything",              loop: true  },
    listening: { caption: "I'm listening…",               loop: true  },
    thinking:  { caption: "Checking the school library…", loop: true  },
    found:     { caption: "Found it!",                    loop: false, red: true },
    notfound:  { caption: "Not on the website. I won't guess.", loop: false },
    talking:   { caption: "Here's what I found",          loop: true  },
  };
  const videos = [document.getElementById("mascot-a"), document.getElementById("mascot-b")];
  const captionEl = document.getElementById("mascot-caption");
  let front = 0;
  let mascotState = null;
  let afterOnce = "idle";        // state to return to when a play-once clip ends

  function clipUrl(state) { return "/static/mascot/" + state + ".mp4?v=" + ASSET_V; }

  function setMascot(state, fallback) {
    if (!MASCOT[state] || state === mascotState) return;
    const spec = MASCOT[state];
    const back = 1 - front;
    const nextVideo = videos[back];
    mascotState = state;
    afterOnce = fallback || "idle";
    nextVideo.loop = spec.loop;
    nextVideo.src = clipUrl(state);
    nextVideo.onended = spec.loop ? null : function () { if (mascotState === state) setMascot(afterOnce); };
    nextVideo.onerror = function () {              // clip missing: keep whatever is showing
      if (mascotState === state) { mascotState = null; }
    };
    const show = function () {
      nextVideo.removeEventListener("canplay", show);
      nextVideo.play().catch(function () { /* autoplay blocked: poster stays */ });
      nextVideo.classList.add("is-front");
      videos[front].classList.remove("is-front");
      front = back;
      setTimeout(function () { videos[back === 0 ? 1 : 0].pause(); }, 400);
    };
    nextVideo.addEventListener("canplay", show);
    nextVideo.load();
    captionEl.textContent = spec.caption;
    captionEl.classList.toggle("is-red", !!spec.red);
  }

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

  // "How I answered": a fold-out under each answer listing the steps the agent
  // really took (library lookup, pages found, Gemini).
  function addSteps(bubble, steps) {
    if (!steps || !steps.length) return;
    const details = document.createElement("details");
    details.className = "how-steps";
    const summary = document.createElement("summary");
    summary.textContent = "How I answered (" + steps.length + " steps)";
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

  // Which reaction fits the answer: the library found pages, found nothing, or
  // the question was general knowledge.
  function reactionFor(steps) {
    const icons = (steps || []).map(function (s) { return s.icon; });
    if (icons.indexOf("🤷") !== -1) return "notfound";
    if (icons.indexOf("📚") !== -1) return "found";
    return "talking";
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
    addBubble(q, "student");
    input.value = "";
    setBusy(true);
    setMascot("thinking");
    const typing = addBubble("Checking the school library…", "bot", "typing");
    const ticker = setTimeout(function () { typing.querySelector(".text").textContent = "Asking Gemini to write the answer…"; }, 1500);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, session_id: sessionId }),
      });
      const data = await res.json().catch(function () { return {}; });
      clearTimeout(ticker);
      typing.remove();
      if (!res.ok) {
        addBubble(data.detail || "Something went wrong. Please try again.", "bot", "error");
        setMascot("notfound");
        return;
      }
      sessionId = data.session_id;
      const bubble = addBubble(data.reply, "bot");
      addSteps(bubble, data.steps);
      lastReply = data.reply;
      prefetchSpeech(lastReply);
      questionCount += 1;
      updateStatus();
      const reaction = reactionFor(data.steps);
      if (autoVoice.checked) {
        setMascot(reaction, "talking");   // react, then keep talking while the voice plays
        speak(lastReply);
      } else {
        setMascot(reaction, "idle");
      }
    } catch (err) {
      clearTimeout(ticker);
      typing.remove();
      addBubble("I can't reach the server right now. Is the app still running?", "bot", "error");
      setMascot("notfound");
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
  function markPlaying() {
    readBtn.classList.add("playing");
    readBtn.title = "Stop";
    readBtn.textContent = "⏹";
    if (mascotState !== "found" && mascotState !== "notfound") setMascot("talking");
    afterOnce = "talking";
  }

  function markStopped() {
    readBtn.classList.remove("playing");
    readBtn.title = "Read the latest answer aloud";
    readBtn.textContent = "🔊";
    afterOnce = "idle";
    if (mascotState === "talking") setMascot("idle");
  }

  function stopAudio() {
    playQueue = [];
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    markStopped();
  }

  // ---------- which voice ----------
  // The badger is a kid, so prefer a youthful male voice and lift the pitch a
  // little. Spanish is Latin American (US / Colombia / Mexico), never Spain.
  // Browser voice lists differ by OS, so each entry is a preference order:
  // exact locale first, then a name hint for the voices we know sound right.
  const VOICE_PREFS = {
    "es-US": {
      locales: ["es-US", "es-CO", "es-MX", "es-419", "es-AR", "es-CL", "es-PE"],
      names: /Alonso|Gonzalo|Jorge|Andr[e\u00e9]s|Mateo|Dalia|Google espa\u00f1ol de Estados Unidos|Paulina|Online|Natural|Google/i,
      avoid: /es-ES|Spain|Espa\u00f1a|Castellano/i,
    },
    "en-US": {
      locales: ["en-US"],
      names: /Andrew|Christopher|Brian|Roger|Guy|Eric|Google US English|Online|Natural|Google/i,
      avoid: /en-GB|en-AU|en-IN|United Kingdom|Australia/i,
    },
  };

  function detectLang(text) {
    return /[\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00bf\u00a1]/i.test(text) ? "es-US" : "en-US";
  }

  function pickVoice(lang) {
    const prefs = VOICE_PREFS[lang];
    const voices = window.speechSynthesis.getVoices().filter(function (v) {
      return !prefs.avoid.test(v.lang + " " + v.name);
    });
    for (let i = 0; i < prefs.locales.length; i++) {
      const same = voices.filter(function (v) { return v.lang.replace("_", "-").toLowerCase() === prefs.locales[i].toLowerCase(); });
      const hit = same.find(function (v) { return prefs.names.test(v.name); }) || same[0];
      if (hit) return hit;
    }
    const anyLang = voices.filter(function (v) { return v.lang.slice(0, 2).toLowerCase() === lang.slice(0, 2); });
    return anyLang.find(function (v) { return prefs.names.test(v.name); }) || anyLang[0] || null;
  }

  function speakWithBrowser(text) {
    if (!("speechSynthesis" in window)) {
      readBtn.title = "Voice not available";
      readBtn.disabled = true;
      autoVoice.checked = false;
      autoVoice.disabled = true;
      return;
    }
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = detectLang(text);
    utter.rate = 1.05;    // a kid talks a touch faster than a newsreader
    utter.pitch = 1.25;   // and higher; 1.0 is the voice's natural pitch
    const voice = pickVoice(utter.lang);
    if (voice) utter.voice = voice;
    utter.onend = markStopped;
    utter.onerror = markStopped;
    window.speechSynthesis.cancel();
    markPlaying();
    window.speechSynthesis.speak(utter);
  }

  // Cloud voice: the reply is split into a short first chunk (one sentence)
  // and the rest, both requested at once, so speech starts after ~1 s instead
  // of waiting for the whole answer to be synthesized. Clips are prefetched
  // the moment an answer arrives, so Read Aloud is instant.
  const ttsClips = {};            // text -> Promise<Blob>
  let playQueue = [];             // Audio elements still to play

  function chunksFor(text) {
    const sentences = text.split(/(?<=[.!?…])\s+/).filter(Boolean);
    if (sentences.length <= 1) return [text];
    return [sentences[0], sentences.slice(1).join(" ")];
  }

  function fetchClip(chunk, lang) {
    if (!ttsClips[chunk]) {
      ttsClips[chunk] = fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: chunk, lang: lang }),
      }).then(function (res) {
        if (!res.ok) throw new Error("tts " + res.status);
        return res.blob();
      });
      ttsClips[chunk].catch(function () { delete ttsClips[chunk]; });
    }
    return ttsClips[chunk];
  }

  function prefetchSpeech(text) {
    if (!cloudTts || !text) return;
    const lang = detectLang(text);
    chunksFor(text).forEach(function (c) { fetchClip(c, lang); });
  }

  function playNext() {
    if (!playQueue.length) { currentAudio = null; markStopped(); return; }
    const audio = playQueue.shift();
    currentAudio = audio;
    audio.onended = playNext;
    audio.onerror = playNext;
    audio.play().catch(playNext);
  }

  async function speak(text) {
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    playQueue = [];
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (!text) return;
    if (cloudTts) {
      // Try Google Cloud Text-to-Speech first; fall back to the browser voice.
      try {
        const lang = detectLang(text);
        const blobs = await Promise.all(chunksFor(text).map(function (c) {
          return fetchClip(c, lang);
        }).map(function (p, i, all) {
          return i === 0 ? p : p.catch(function () { return null; });   // start on chunk 1 even if 2 lags
        }));
        playQueue = blobs.filter(Boolean).map(function (b) { return new Audio(URL.createObjectURL(b)); });
        markPlaying();
        playNext();
        return;
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
  // After the student stops talking (the browser waits for about a second of
  // silence), we send the sentence ourselves after a 1-second countdown, so
  // nobody has to press Send: roughly two seconds from the end of the question.
  // Clicking the box, typing, or clicking the mic cancels the countdown.
  const AUTO_SEND_SECONDS = 1;
  let autoSendTimer = null;

  function cancelAutoSend() {
    if (autoSendTimer) { clearInterval(autoSendTimer); autoSendTimer = null; }
    sendBtn.textContent = "➤";
    sendBtn.title = "Send";
  }

  function armAutoSend(text) {
    cancelAutoSend();
    if (!text || text.trim().length < 3) return;
    let left = AUTO_SEND_SECONDS;
    sendBtn.textContent = String(left);
    sendBtn.title = "Sending in " + left + "…";
    autoSendTimer = setInterval(function () {
      left -= 1;
      if (left > 0) { sendBtn.textContent = String(left); return; }
      cancelAutoSend();
      ask(input.value);
    }, 1000);
  }
  input.addEventListener("input", cancelAutoSend);
  input.addEventListener("pointerdown", cancelAutoSend);

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
        cancelAutoSend();
        recognizer = new Recognition();
        recognizer.lang = "en-US";
        recognizer.interimResults = false;
        recognizer.maxAlternatives = 1;
        recognizer.onresult = function (event) {
          const text = event.results[0][0].transcript;
          input.value = text;           // show it so it can be fixed before sending
          armAutoSend(text);            // ...and send it after a short countdown
        };
        recognizer.onerror = function () {
          input.placeholder = "Microphone didn't work. Please type your question.";
        };
        recognizer.onend = function () {
          recognizer = null;
          micBtn.classList.remove("listening");
          micBtn.title = "Ask with your voice";
          if (mascotState === "listening") setMascot("idle");
        };
        micBtn.classList.add("listening");
        micBtn.title = "Listening… click to stop";
        setMascot("listening");
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
    statusEl.textContent = "Model " + health.model + " · Voice " + (cloudTts ? "Google Cloud" : "browser") +
      " · Library " + health.knowledge_pages + " pages" +
      (questionCount ? " · Questions " + questionCount : "");
  }
  fetch("/api/health")
    .then(function (r) { return r.json(); })
    .then(function (h) {
      health = h;
      cloudTts = !!h.cloud_tts;
      updateStatus();
    })
    .catch(function () { statusEl.textContent = "Server not reachable"; });

  setMascot("wave", "idle");
  input.focus();
})();
