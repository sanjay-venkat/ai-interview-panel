# Voice Verse Bot

**Three AI interviewers. One live conversation. Zero scripted turns.**

Most "AI interview" products are a single chatbot wearing a name tag, working
down a fixed question list. Voice Verse Bot is a real panel — a Technical
Lead, a Hiring Manager, and a Culture & Values Partner — sharing one live
voice room with the candidate, listening together, remembering together, and
deciding together who should speak next.

---

## What makes it different

- **A panel that actually behaves like one.** There's no round-robin script.
  Every interviewer is continuously scored on relevance to what the
  candidate just said, and speaking priority itself shifts with the role
  being interviewed for — a Technical Lead carries more weight for an
  engineering role, a Culture & Values Partner for HR. Nobody "waits their
  turn"; the floor goes to whoever the moment actually calls for.
- **Real personas, not placeholders.** Each interviewer has a static avatar,
  a name, and a designation, and speaks in its own distinct voice — with one
  consistent, unmistakable "speaking" cue, so it's always clear who has the
  floor.
- **Live, not simulated.** Real-time voice with genuine interruptions and
  barge-in — the candidate and the panel can actually talk over each other,
  the way a real interview does.
- **Private by design.** Webcam integrity monitoring runs entirely on-device
  in the browser. No video is ever uploaded, streamed, or stored.
- **A scorecard you can actually learn from.** Six scored dimensions, and you
  can click any one of them to see exactly why it landed there and what
  would raise it — no black-box number.
- **See your shape, not just your score.** An interactive radar chart
  expands full-screen on click, so a candidate can spot their strongest and
  weakest areas at a glance instead of parsing six numbers.
- **Walk away with something.** One click exports a complete PDF — panelist
  comments, the full score breakdown, and the radar chart — a real
  take-home, not a screenshot.
- **A panel built for the role, not a generic one.** Nine role templates
  ship out of the box (engineering, data, research, product, HR, and more),
  each assembling a differently-focused panel automatically.
- **Runs with zero API keys.** A full offline mode lets you demo the entire
  experience — UI, live turn-taking, the final scorecard — before a single
  account is ever wired up.

## Built with

Real-time voice via **Agora**, speech recognition via **Deepgram**, response
generation via **Groq**, and natural, swappable text-to-speech (**Cartesia**
by default, **ElevenLabs** optional) — orchestrated behind a **FastAPI**
backend and a **Next.js** frontend.

---

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# fill in .env with the keys from the table below
python run.py
```

Runs on `http://localhost:8000`. Check `http://localhost:8000/health` —
`mock_mode: true` means no API keys were found, so the panel runs on canned
responses while everything else (turn-taking, live state, the scorecard)
behaves exactly as it would live.

In a second terminal, start a tunnel and paste the URL into `.env`:

```bash
ngrok http 8000
# copy the https://xxxx.ngrok-free.app URL into PUBLIC_BACKEND_URL in .env,
# then restart python run.py so it picks up the new value
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Runs on `http://localhost:3000`.

### Try it with zero setup first

With no API keys configured at all, the app still runs end to end on canned
responses — the fastest way to see the panel, the live transcript, and the
scorecard work before wiring up a single account.

---

## What you'll need

| # | What | Where | Notes |
|---|------|-------|-------|
| 1 | Agora **App ID** + **App Certificate** | [Agora Console](https://console.agora.io) → Project Management | Powers the real-time voice room |
| 2 | Agora **Customer ID** + **Customer Secret** | Agora Console → project Home → "Manage credentials" | A separate credential pair from #1 — this authorizes the Conversational AI Engine |
| 3 | **Deepgram** API key | [console.deepgram.com](https://console.deepgram.com) | Free tier covers speech recognition |
| 4 | **Cartesia** API key + 3 voice IDs | [play.cartesia.ai/keys](https://play.cartesia.ai/keys) | Default voice vendor — pick three distinct voices so the panel sounds like three different people |
| 5 | **Groq** API key | [console.groq.com/keys](https://console.groq.com/keys) | Free tier, powers response generation |
| 6 | A public tunnel (**ngrok** or **cloudflared**) | `ngrok http 8000` | Required for local development — Agora's cloud needs a public URL to reach your backend |

Enable **Conversational AI Engine** on your Agora project if it isn't on by
default (Console → your project → look for a ConvoAI / Agent section).

The voice vendor is fully swappable — one env var
(`TTS_VENDOR=cartesia|elevenlabs`) switches it, no code changes needed.
Cartesia is the default because its free tier handles real-time streaming
cleanly for a panel this size; ElevenLabs works well too on a paid plan.

---

## Deploying

### Backend → Render

A `render.yaml` blueprint at the repo root describes the service end to end,
so Render can provision it in one pass.

1. Push this repo to GitHub.
2. On [render.com](https://render.com), **New → Blueprint**, pick this repo.
3. Fill in the env vars Render asks for (the same ones from your local
   `.env`) directly in its dashboard — never paste secrets into chat or
   docs.
4. Once live, set `PUBLIC_BACKEND_URL` to your Render URL and
   `CORS_ORIGINS` to your deployed frontend's URL, then redeploy.

Free tier spins down after 15 minutes idle and cold-starts in about a
minute — ping `/health` before a live demo to warm it up.

### Frontend → Vercel

Import the repo, set **Root Directory** to `frontend`, add
`NEXT_PUBLIC_BACKEND_URL` pointing at your backend, and deploy.

---

## What's next

Claim-tracking follow-up questions, richer resume-aware questioning, account
persistence beyond a single session, and spoken (not just written)
deliberation are the natural next steps — the core experience is already
built to support all four without a redesign.
