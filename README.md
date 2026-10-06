# 35th Med Simulator Asklepios

Networked **Tactical Combat Casualty Care (TCCC)** training simulator for 35th Fighter Wing Medical Group personnel.

**Training simulation only — not for operational use, direct patient care, or clinical decision support.**

Providers train on phone-sized bedside workflows. WIT evaluators configure and deploy scenarios. Command staff observe exercise-wide status. Lobbies work like an “Among Us” room code: host creates a 6-character code, providers join with that code.

## Source

Seeded from [SDF-01/ProjectAsklepios](https://github.com/SDF-01/ProjectAsklepios) for wing-hosted development on git.mil.

| Layer | Location |
|-------|----------|
| Frontend | `src/` — React 19, Vite 6, Tailwind 4, Zustand, React Router |
| Simulation engines | `src/engines/` — vitals, triage, supply, AAR (runs in the browser) |
| Hub | `server/` — Express + Socket.IO lobbies and device sync (in-memory) |
| Content | `content/exercises/toon/` → generated catalog (100 exercises) |

## Local development

```bash
npm install
npm run dev
```

| Role | URL |
|------|-----|
| Hub API | http://localhost:3021/api/health |
| Provider (phones) | http://localhost:5183 |
| WIT / host | http://localhost:5184/host |

Phones on the same Wi‑Fi: `http://<laptop-ip>:5183/join`

### Quick exercise test

1. Open WIT → `/host` → **Create exercise** → copy the 6-character code.
2. Open provider → `/join` → enter code → save profile.
3. WIT opens the console and deploys a scenario.

## Planned work (this repo)

1. **Solo practice mode** — pick a scenario and run brief → simulation → AAR with no hub.
2. **Offline / PWA hardening** — self-hosted fonts, service worker, install icons.
3. **Free multiplayer hosting** — fix Render hub start (`tsx` / install), prefer single-service static+hub or Cloudflare Pages + Render; keep-alive for free-tier sleep.
4. Leave multi-role handoff chains out of solo mode initially (pass-and-play later).

## Notes

- Simulation logic already runs in the browser. The hub is for lobby join, deploy, and multi-device sync.
- Hub state is in memory: a restart clears active lobbies.
- Vercel serverless is not a reliable Socket.IO host for this hub.

## License / use

Private / training use for 35th Fighter Wing Medical Group. See repository owners for distribution terms.
