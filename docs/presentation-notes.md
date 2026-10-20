# Presentation Notes (for the presenter)

These are talking aids. They are **not** part of the chatbot's answers.

## Analogies to use on stage

| Thing on screen | Say this |
|---|---|
| `app/agent.py` | **Code = instructions.** "The app you're using came from instructions like these." |
| Gemini | **The brain.** It reads the facts and writes a friendly answer. |
| `app/school_knowledge.json` | **The library.** A saved copy of the public school website. The AI may only use what it finds here. |
| `/api/chat`, Vertex AI API | **A messenger.** Carries the question to the brain and the answer back. |
| Cloud Run (or your laptop) | **Where the app lives.** |
| Google Cloud | **A giant building full of computers** that anyone can rent by the second. |
| You | **The Cloud Architect:** the person who decides how all the pieces fit together. |

## The slide deck

`docs/Career_Day_2026_EWMS.pptx` (45 minutes, speaker notes on every slide).

| Slide | What changed for the chatbot |
|---|---|
| 9 · Can the AI pass the Badger Test? | Live demo. The dark **🌉 Badger Test** chip under the chat sends the exact question on the slide. QR code + address on the right so phones can follow along. |
| 10 · The plan I drew for Badger AI | The Google Cloud architecture with numbered stickers and a plain-English legend. One sentence per number, then move on (about 1 minute). |
| 16 · Ask me anything | QR code + address again so students can keep chatting. |

Before the day: `python scripts/set_deck_chat_url.py https://YOUR-SERVICE.a.run.app`
replaces the placeholder address and both QR codes.

## The four "wow moments"

1. **CODE** – open `app/agent.py`, lines 21–43 ("This connects our chatbot to school information") and lines 46–56 ("This tells our AI how to behave"). Scroll slowly. Point out the rules are written in English.
2. **CLOUD** – slide 10 in the deck, or `docs/architecture-student.svg`, or the Google Cloud console pages listed in the README. One sentence per box.
3. **AI INTERACTION** – hand the keyboard to a student. Click **🔊 Read Aloud** next to the text box, or switch **Auto voice** on (top right) so every answer is spoken. The **🌎** chip shows the bot answering in Spanish.
4. **BEHIND THE SCENES** – after any answer, click **🔍 How I answered**. Students see the agent open the library, which pages it found (or "nothing on the website"), and Gemini writing the answer. Say: "That is the plan on slide 10, happening live."

## Suggested script (≈6 minutes)

1. "Who has used a chatbot before?" Show the page. Click **What is our mascot?**
2. Click **🔊 Read Aloud**. Let it finish. Click it again (**⏹ Stop**) to show you're in control. Then flip **Auto voice** on for the rest of the demo.
3. Switch to the code. "You don't need to understand this. Notice it's just instructions."
4. Switch to the diagram. "My job is deciding how these boxes connect, and keeping it safe and affordable."
5. Students ask questions. Keep the **challenge question** ready: the **🌉 Badger Test** chip
   (*"Tell me about the famous Badger Bridge at Ed Willkie Middle School, built in 1901."*) or
   *"Who won the 7th grade spelling bee last year?"* The bot must say it couldn't find that on the website. Open **How I answered** to prove it looked. Explain: "A good AI app is built to say 'I don't know' instead of making things up. That's a design decision an architect makes."
6. Close with career questions: *"Do I have to be good at math?"*, *"What should I learn?"*

## Backup plan

| If this fails | Do this |
|---|---|
| Microphone | Type the question (the mic button simply hides itself). |
| Read Aloud | Read the answer from the screen. |
| School website | Nothing changes: the library is saved in the repo. |
| Wi-Fi / API key | Show the pre-recorded answers printed by `python scripts/career_day_check.py` (run it the night before and keep the output; it includes the Badger Test and the Spanish question). |
| Phones can't reach the QR address | Nothing changes: the demo runs on the laptop. Tell students the address is on the last slide. |
| Cloud Run deployment | Run locally with `make dev` (that is the primary plan anyway). |

## Privacy reminders

- Say out loud: "This is an AI demo. Don't type your name."
- Nothing is saved: no accounts, no chat history on disk, no audio recordings.
