# AI Interview Panel

Two AI interviewers (Technical Lead + Hiring Manager) share one live Agora RTC
channel with a candidate. Agora's **Conversational AI Engine** runs the voice
pipeline (STT via Deepgram, TTS via a pluggable vendor — Cartesia by default,
VAD, barge-in) for each agent. Our backend is the "brain": a deterministic
floor controller decides who speaks next, a shared conversation-state object
gives both agents memory of what's been said, and Groq (free tier,
`llama-3.1-8b-instant`) generates each agent's actual question/response.

Full architecture rationale is in the conversation that produced this repo;
this file is the practical setup + status doc.

## What's built

- **Backend** (`backend/`, FastAPI): session lifecycle, Agora RTC token
  generation, Agora ConvoAI agent join/leave, the OpenAI-compatible `/llm/*`
  proxy endpoint both agents call, the floor controller, shared conversation
  state, WebSocket state broadcast, end-of-interview deliberation/scorecard.
- **Frontend** (`frontend/`, Next.js + TypeScript): setup screen, Agora Web
  SDK join (mic publish + subscribe to both agent audio tracks), live
  transcript, agent speaking/listening indicators, topic confidence bars,
  latency HUD, final scorecard screen.
- **Mock mode**: works fully offline with zero API keys (`MOCK_MODE=true` or
  simply no `GROQ_API_KEY` set) — canned responses flow through the *real*
  floor-controller/state/WebSocket pipeline, so you can build and demo the UI
  and turn-taking logic before any accounts are wired up.

Verified so far (see "Day-1 validation" below for what's *not* yet verified
against live Agora infra): floor-controller race handling under true
concurrency, full session lifecycle (start → turns → end → scorecard) via
HTTP, backend installs cleanly, frontend type-checks and production-builds
cleanly.

## What's NOT built (by design — see the cut-scope list from the plan)

Claim-tracker challenge questions, resume upload/parsing, auth, persistence
beyond process memory, deliberation *audio* (scorecard is text-only), mobile
layout polish. These are reasonable Phase-2+ additions, not needed for a
working demo.

---

## What you need to obtain

| # | What | Where | Notes |
|---|------|-------|-------|
| 1 | Agora **App ID** + **App Certificate** | [Agora Console](https://console.agora.io) → Project Management → create project (enable "App Certificate" / secured mode) | Used for RTC tokens |
| 2 | Agora **Customer ID** + **Customer Secret** | Agora Console → Developer Toolkit → RESTful API → Add a secret | Different credential pair from #1 — this is Basic-auth for the Conversational AI Engine REST calls, not the RTC token |
| 3 | **Deepgram** API key | [console.deepgram.com](https://console.deepgram.com) | Free tier is fine for STT |
| 4 | **Cartesia** API key + 2 voice IDs | [play.cartesia.ai/keys](https://play.cartesia.ai/keys) | **TTS, default vendor.** Free tier gives 2 concurrent real-time streams — exactly our two-agent case — plus sub-90ms latency (their Sonic model). Pick two different voices at [play.cartesia.ai/voices](https://play.cartesia.ai/voices) so the two interviewers sound distinct. |
| 5 | **Groq** API key | [console.groq.com/keys](https://console.groq.com/keys) | Free tier, used for `llama-3.1-8b-instant` |
| 6 | A public tunnel (**ngrok** or **cloudflared**) | `ngrok http 8000` | Agora's cloud calls *your* `/llm/*` endpoint — it cannot reach `localhost`. This is easy to forget and will silently break everything if skipped. |

Enable **Conversational AI Engine** on your Agora project if it's not on by
default (Console → your project → check for a ConvoAI / Agent section; new
projects usually have it available already).

### Why Cartesia instead of ElevenLabs by default

The TTS vendor is fully pluggable (`backend/app/agora/tts_vendors.py`,
switched with one env var: `TTS_VENDOR=cartesia|elevenlabs`) — you're not
locked into either. Cartesia is the default because its free tier actually
supports real-time streaming for our exact shape (2 concurrent agents);
**ElevenLabs' free tier is routinely blocked by Agora's abuse-detection for
real-time streaming and will silently kill audio mid-demo.** If you already
have a paid ElevenLabs plan and prefer its voice quality/variety, set
`TTS_VENDOR=elevenlabs` and fill in the ElevenLabs keys instead — no code
changes needed. Starting a session with a misconfigured vendor (missing key
for whichever `TTS_VENDOR` you selected) now fails immediately with a clear
400 error instead of failing silently once agents are already live.

---

## Setup

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# fill in .env with the keys from the table above
python run.py
```

Runs on `http://localhost:8000`. Check `http://localhost:8000/health` —
`mock_mode: true` means no `GROQ_API_KEY` was found (or `MOCK_MODE=true` was
set), so responses will be canned but the whole pipeline still runs.

In a second terminal, start the tunnel and paste the URL into `.env`:

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

### Try it in mock mode first

With `MOCK_MODE=true` and no Agora credentials at all, `POST /session/start`
still returns a session (with empty `app_id`/`candidate_token`), and you can
drive `/llm/{agent_id}/{session_id}/chat/completions` directly with curl to
watch the floor controller, transcript, and scorecard work — before touching
any real audio. This is the fastest way to validate the "brain" without
burning API calls or fighting audio issues first.

---

## Deploying to production

Once the local + ngrok flow works end-to-end, swap the tunnel for real hosting
so the demo doesn't depend on your laptop staying online.

### Backend → Render (or Railway / Fly.io — anything that builds a Dockerfile)

A `backend/Dockerfile` is included.

1. Push this repo to GitHub.
2. On [Render](https://render.com): New → Web Service → connect the repo →
   root directory `backend` → Render auto-detects the `Dockerfile`.
3. Add every var from `backend/.env.example` in Render's Environment tab.
   Leave `PUBLIC_BACKEND_URL` blank for now — you'll fill it in after step 4.
4. Deploy. Copy the resulting `https://your-service.onrender.com` URL.
5. Set `PUBLIC_BACKEND_URL` to that URL (no trailing slash) and redeploy —
   this is what Agora's ConvoAI engine calls for `/llm/*`, so it must be the
   live URL, not localhost/ngrok, before you start a real session.
6. Set `CORS_ORIGINS` to your deployed frontend's URL (from the Vercel step
   below) once you have it, and redeploy again.

Note: Render/Railway free tiers can cold-sleep after inactivity, which adds
latency to the first request. Ping `/health` before a live demo to warm it up.

### Frontend → Vercel

1. On [Vercel](https://vercel.com): New Project → import the same repo → set
   root directory to `frontend` (Next.js auto-detected).
2. Add environment variable `NEXT_PUBLIC_BACKEND_URL` = your Render backend
   URL from above.
3. Deploy. Copy the resulting `https://your-app.vercel.app` URL and use it
   for `CORS_ORIGINS` on the backend (step 6 above).

### After both are live

Re-run the Day-1 validation checklist below against the deployed URLs, not
localhost — a misconfigured `CORS_ORIGINS` or stale `PUBLIC_BACKEND_URL` is
the most common way a working local demo breaks in production.

---

## Day-1 validation checklist (do these before building anything else)

These are the specific behaviors that Agora's public docs don't fully
document, or that only real, paid vendor accounts can confirm. Test them in
this order, cheapest/fastest first:

1. **Empty-content "pass" doesn't produce audio.** When the losing agent's
   `/llm/*` call returns an empty-content SSE chunk with `finish_reason:
   "stop"` (see `backend/app/api/llm_proxy.py::_pass_stream`), confirm the
   TTS vendor/Agora genuinely stays silent rather than erroring or emitting a
   blip. If it doesn't, the fallback is to make the "pass" response a single
   short breath/filler sound instead of true empty content.
2. **Two simultaneous ConvoAI agents in one channel behave as expected** —
   that both can publish audio into the same channel without Agora rejecting
   the second `join`, and that each agent's ASR only transcribes the
   candidate's audio (not the other agent's TTS output, which would create a
   feedback loop). `remote_rtc_uids` in the join payload is what scopes each
   agent to listen only to the candidate — verify this scoping actually holds.
3. **Two greeting messages don't overlap.** Only `technical_lead` is
   configured with a `greeting_message` in `session_manager.py`;
   `hiring_manager`'s first line is generated dynamically on its forced first
   turn instead. Confirm this avoids audio collision on join.
4. **`PUBLIC_BACKEND_URL` reachability.** Agora's servers must be able to
   reach your ngrok URL — test with `curl https://your-ngrok-url/health` from
   *outside* your network (e.g. your phone on cellular) before relying on it.
5. **TTS streaming actually works on your plan tier.** Cartesia's free tier
   is generally fine for this (see above), but its free plan is also
   non-commercial-use only — read their terms if that matters for how you're
   presenting the hackathon project. If you switch to ElevenLabs, confirm
   your plan tier isn't rate-limited/blocked before the demo.

## Architecture reference

```
Candidate mic → Agora RTC channel ← 2 Agora ConvoAI agents (Technical Lead, Hiring Manager)
                                          │            │
                                    Deepgram ASR   Deepgram ASR (independent per agent)
                                          │            │
                                          ▼            ▼
                              POST /llm/technical_lead/{sid}/chat/completions
                              POST /llm/hiring_manager/{sid}/chat/completions
                                          │            │
                                          ▼            ▼
                                 floor_controller.resolve_decision (shared, epoch-deduped)
                                          │
                              winner streams a real Groq response (SSE)
                              loser streams an empty "pass" (SSE)
                                          │
                                          ▼
                    TTS vendor (Cartesia by default) (Agora-managed) → RTC → candidate
```

Deterministic Python code (floor control, state, session lifecycle) owns the
application; the LLM only ever answers "what should this specific agent say
right now," never "who should speak" or "what happens next" — see
`app/orchestration/floor_controller.py` for why that split matters for both
latency and reliability.
