# Agent assignment sheet — 35th Med Simulator Asklepios

Work only in this repo (`sync.git.mil/35th-weaselwerx/35th-med-simulator-asklepios`). Leave `SDF-01/ProjectAsklepios` alone.

**Author every commit as:** `Kubinski, Joseph W TSgt USAF (USA) <joseph.kubinski@us.af.mil>`  
(repo-local git config is already set)

**Open MRs into `main`.** Do not force-push `main`.

---

## Priority order

| # | Stream | Branch | Status |
|---|--------|--------|--------|
| 1 | Solo practice | `feat/solo-practice-mode` | In progress / MR |
| 2 | Offline / PWA | `feat/pwa-offline` | Ready for agent |
| 3 | Local history | `feat/local-history` | Ready for agent |
| 4 | Hosting fix | `fix/render-hub-hosting` | Partial (`render.yaml` in solo branch) |
| 5 | Solo handoffs | deferred | Do not start |

---

## Agent 1 — Solo practice (this branch)

**Done when:** landing has Solo practice → `/solo` → configure → brief → sim → AAR with hub no-ops; host/join clear solo flag.

**Do not touch:** `formal/`, CI assurance scripts, facility-arrival generators.

---

## Agent 2 — Offline / PWA (`feat/pwa-offline`)

**Scope**
- Self-host fonts (replace Google Fonts CDN in `index.html`)
- Add `vite-plugin-pwa` (or equivalent already in ecosystem) for SW + precache of `public/data/**`
- Fix `cache: 'no-store'` in ScenarioLibrary / scenarioLibrary fetches so offline works
- Add PNG icons referenced from `public/manifest.webmanifest`

**Do not touch:** solo mode files unless merge conflict; `server/`; formal proofs.

**Accept:** `npm run build` (or `tsc -b` + `vite build` if generate gates fail for unrelated reasons); app loads with network offline after one online visit.

---

## Agent 3 — Local history (`feat/local-history`)

**Scope**
- Zustand `persist` for completed AAR / recent solo sessions (localStorage)
- Simple “Past practices” list reachable from `/solo` or landing
- Clear / limit retention (e.g. last 20)

**Do not touch:** hub protocol; PWA plugin setup (coordinate with Agent 2 if both touch store).

**Accept:** reload browser, past AAR still listed; no secrets in storage.

---

## Agent 4 — Hosting docs (`fix/render-hub-hosting`)

**Scope**
- Confirm `render.yaml` uses `npm ci --include=dev` (may already be on solo branch; rebase)
- Document Cloudflare Pages + Render hub vs single Render static+hub in README
- Optional: `express.static('dist')` SPA fallback on hub for single-service option
- Note UptimeRobot keep-alive for free-tier sleep

**Do not touch:** solo UI; PWA.

---

## Collision rules

- One branch per agent; rebase on `main` before MR.
- Prefer small MRs.
- If two agents need `simulationStore.ts`, Agent 1 merges first; others rebase.
