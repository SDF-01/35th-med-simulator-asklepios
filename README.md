# 35th Med Simulator Asklepios

Networked **Tactical Combat Casualty Care (TCCC)** training simulator for 35th Fighter Wing Medical Group personnel.

**Training simulation only: not for operational use, direct patient care, or clinical decision support.**

Providers train on phone-sized bedside workflows. WIT evaluators configure and deploy scenarios. Command staff observe exercise-wide status. Lobbies work like an “Among Us” room code: host creates a 6-character code, providers join with that code.

## Source

Seeded from [SDF-01/ProjectAsklepios](https://github.com/SDF-01/ProjectAsklepios) for wing-hosted development on git.mil.

| Remote | URL | Role |
|--------|-----|------|
| `origin` | [git.mil wing repo](https://web.git.mil/35th-weaselwerx/35th-med-simulator-asklepios) | Canonical |
| `github` | [SDF-01/35th-med-simulator-asklepios](https://github.com/SDF-01/35th-med-simulator-asklepios) | Private mirror for Render |

Push both after finishing work on `main` (no auto-sync yet):

```bash
git push origin main
git push github main
```

| Layer | Location |
|-------|----------|
| Frontend | `src/`: React 19, Vite 6, Tailwind 4, Zustand, React Router |
| Simulation engines | `src/engines/`: vitals, triage, supply, AAR (runs in the browser) |
| Hub | `server/`: Express + Socket.IO lobbies and device sync (in-memory) |
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

### Solo practice (no hub)

1. Open http://localhost:5183/solo (or **Solo practice** on the landing page).
2. Configure a scenario → **Start solo practice**.
3. Run brief → simulation → after-action review on the same device.

Completed AAR summaries are saved in browser localStorage (up to 20 entries) under **Past practices** on `/solo`. Clear history from that panel. Device-local only; not synced to the hub.

Multi-role handoff chains are not included in solo mode yet.

### Quick multiplayer exercise test

1. Open WIT → `/host` → **Create exercise** → copy the 6-character code.
2. Open provider → `/join` → enter code → save profile.
3. WIT opens the console and deploys a scenario.

### Offline / PWA

Production builds register a service worker (`vite-plugin-pwa`) that precaches the app shell and static files under `public/data/**`. Fonts are self-hosted via `@fontsource` (Source Sans 3 and IBM Plex Mono); there is no Google Fonts CDN dependency.

After one online visit to a production or `vite preview` build, scenario library JSON and the UI shell should load offline. Multiplayer lobbies still need the hub online. Installable icons live in `public/icons/` and are listed in `public/manifest.webmanifest`.

## Free multiplayer hosting

The hub needs a long-lived Node process (Socket.IO). The SPA can live on a separate static host or on the same Render service.

### Option A (recommended when SPA is separate): Cloudflare Pages + Render hub

1. Deploy the Vite SPA to Cloudflare Pages (`npm run build:bundle` or full `npm run build`).
2. Deploy the hub from Render (Blueprint or manual). For hub-only, use build `npm ci --include=dev` (no `build:bundle`), start `npm run start:hub`, health `/api/health`.
3. Set hub env `ASKLEPIOS_CORS_ORIGIN` to the Pages origin (comma-separated if you also allow localhost).
4. Set SPA env `VITE_HUB_URL` to the Render hub origin (rebuild the SPA after changing it).

Note: the checked-in `render.yaml` defaults to Option B (SPA + hub). For Option A, change the Render build command to omit `&& npm run build:bundle`.

### Option B: Single Render service (static + hub)

`render.yaml` is configured for this path (preferred for a new Render account):

1. Build: `npm ci --include=dev && npm run build:bundle` so `dist/` exists.
2. Start: `npm run start:hub`. When `dist/index.html` is present, the hub serves the SPA and keeps `/api/*` plus Socket.IO working.
3. Set `ASKLEPIOS_CORS_ORIGIN` to this service's public HTTPS origin (update the Blueprint placeholder after first deploy if the hostname differs).
4. Leave `VITE_HUB_URL` empty so the browser uses same-origin hub URLs.

**Git source note:** Render cannot pull from private git.mil. Use a public GitHub mirror/fork, connect a private GitHub repo Render can access, or create the web service manually and paste build/start settings from `render.yaml`.

### Keep-alive (free tier)

Render free web services sleep after idle time. Point [UptimeRobot](https://uptimerobot.com/) (or similar) at `GET https://<your-hub>/api/health` every ~5 minutes so lobbies stay warm during training windows.

## Planned work (this repo)

1. ~~**Solo practice mode**~~: `/solo` available for single-device practice without the hub.
2. ~~**Offline / PWA hardening**~~: self-hosted fonts, service worker, install icons (see Offline / PWA above).
3. ~~**Local history**~~: past AAR/practice summaries in localStorage (`practiceHistoryStore`, `/solo`).
4. ~~**Free multiplayer hosting**~~: `render.yaml` + hosting docs (Cloudflare Pages + Render, or single Render SPA+hub).
5. **Solo handoffs**: pass-and-play or in-browser lobby stand-in (deferred).

## Notes

- Simulation logic already runs in the browser. The hub is for lobby join, deploy, and multi-device sync.
- Hub state is in memory: a restart clears active lobbies.
- Vercel serverless is not a reliable Socket.IO host for this hub.

## License / use

Private / training use for 35th Fighter Wing Medical Group. See repository owners for distribution terms.
