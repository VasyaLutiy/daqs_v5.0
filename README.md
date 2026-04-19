# DAQS v5.0: The Unified Neuro-Symbolic Engine

**DAQS (Deterministic Adaptive Quest System)** is a hybrid game engine that combines deterministic planning logic (PDDL) with LLM creativity.

Version 5.1 (enterprise split) keeps all planning/world logic server-side (FastAPI) and exposes a thin Streamlit client.

## About the project
We built DAQS for the Gemini hackathon to bridge a gap we kept seeing: rigid scripted NPCs feel fake, while free-form LLM NPCs hallucinate, forget inventory, and break quest chains. DAQS pairs Gemini for natural language with a PDDL planner for provable game logic, so characters improvise while every move is mathematically grounded.

### Inspiration
Modern AI NPCs talk well but act poorly. Inspired by GOAP systems (F.E.A.R., S.T.A.L.K.E.R.) and Gemini’s multimodal stack, we asked: what if NPCs spoke with Gemini but thought with a planner? That “two-brain” idea—LLM for style, PDDL for truth—became DAQS.

### How we built it
- **Neuro-symbolic core:** We model each session as a PDDL tuple \(\Pi = \langle O, I, G \rangle\) where operators \(O\) cover moves like `move`, `pickup`, `persuade`, \(I\) is the live state (location, inventory, mood), and \(G\) encodes quest goals. Plans \(\pi = \langle a_1, a_2, \dots, a_k \rangle\) come from unified_planning/Fast Downward.
- **Gemini front-end:** Gemini classifies player intent, renders narrative around validated PDDL actions, and keeps to a Valid Moves list injected into prompts.
- **Game as Code:** Worlds, items, and personas live in YAML. The engine hot-swaps personas and regenerates graphs instantly.
- **Client/server split:** FastAPI backend hosts the world and planner; Streamlit UI runs the Game Master front-end.

### Challenges we faced
- **Neuro-symbolic mapping:** Getting Gemini to emit stable predicates (e.g., `(user-negative)`) required a strict extraction schema and guardrails.
- **Hallucination control vs. creativity:** We anchored Gemini with planner-approved metadata so it never invents NPCs or items, yet keeps flavor.
- **Latency:** Classical planning can be slow; domain pruning plus unified_planning kept responses under ~200 ms.

### What we learned
Constraining creativity with structure actually amplifies it: Gemini can focus on storytelling while the planner enforces causality. Modeling “mood” and social states as predicates turns dialogue into tactical play—social chess instead of free-form improv.

## 🧠 Architecture: “Two Brains”

The project is split into two independent layers that work together:

1. **World Engine (The Body):**
    * Manages player movement between locations.
    * Runs as a stateless FastAPI server.
    * Uses PDDL for pathfinding and validating physical actions.
2. **Social Engine (The Soul):**
    * Activates when talking to “story” NPCs.
    * Manages the graph of mental states (Intro -> Deep -> Core).
    * Implements “Game as Code”: the LLM is constrained by strict rules (tags, locks, inventory).

## 🚀 Quick Start

Dependencies are required (`pip install -r requirements.txt`) plus a `GEMINI_API_KEY` environment variable.

### 1. Launch the logic server (Backend, enterprise)
```bash
export NPC_API_BASE="http://localhost:8001"  # optional; default matches below
cd npc_engine
uvicorn main_fast_ent:app --host 0.0.0.0 --port 8001
```

### 2. Launch the interface (Frontend, thin client)
```bash
# From the repo root
streamlit run social_webui_ent.py

# Enable visuals (image gen) with -- --visual if your env supports it
streamlit run social_webui_ent.py -- --visual
```

## 🛠 Key Features in v5.0
* **The Oracle Prologue**: NPC auto-generates a quest prophecy by analyzing the PDDL graph.
* **Mini-Map**: Live visualization of the location graph with fog of war.
* **Auto-Enter Logic**: Seamless entry into new contexts when they unlock.
* **Persistence**: Auto-saving player state to `player_state.json`.
* **Global Triggers**: Ability to discuss core topics (Axioms) in any location.

## 📂 Project Structure
* `gamemaster/`: Social engine logic, prompts, and orchestrator.
* `npc_engine/`: World engine logic, FastAPI servers, and PDDL generators.
    * `main_fast_ent.py`: Enterprise FastAPI entrypoint (all planner/world logic).
    * `fastapi_ent_libs.py`: Shared helpers for the enterprise server.
* `social_webui_ent.py`: Thin Streamlit client that talks to `main_fast_ent`.
* `player_state.json`: Current game save.

---
Developed by VasyaLutiy & AI Architect.

## CI/CD (Prod -> single Docker container)

This repo now includes GitHub Actions pipelines:

- `CI` (`.github/workflows/ci.yml`)
  - Runs on pull requests to `main`/`Prod` and on pushes to non-`Prod` branches.
  - Installs dependencies, runs focused phase tests, builds Docker image.

- `CD-Prod` (`.github/workflows/cd-prod.yml`)
  - Runs only on push to branch `Prod` (or manual `workflow_dispatch`).
  - Builds image and pushes to `ghcr.io/<owner>/<repo>` with tags:
    - `prod-latest`
    - `sha-<commit_sha>`
  - Deploys to one remote container named `daqs` over SSH.

### Required GitHub Secrets

Set these in repository settings (`Settings -> Secrets and variables -> Actions`):

- `PROD_HOST` - production server host/IP
- `PROD_USER` - SSH user
- `PROD_SSH_KEY` - private SSH key (PEM/OpenSSH)
- `PROD_PORT` - SSH port (usually `22`)
- `PROD_ENV_FILE` - full `.env` content for production container
- `GHCR_USERNAME` - GitHub username/org allowed to pull GHCR image
- `GHCR_TOKEN` - token with `read:packages` for GHCR pull on server

### Deploy flow

1. Merge your working branch into `Prod`.
2. Push `Prod`.
3. GitHub Actions builds image and deploys it to the server.
4. Workflow validates `http://localhost:8001/health` on the server.

### Manual deploy first (docker compose, no CI/CD)

Run on production server inside repo directory:

```bash
git fetch origin
git checkout Prod
git pull --ff-only origin Prod
cp env.example .env   # once; then edit .env with real production values
docker compose up -d --build
```

Or use helper script:

```bash
./scripts/deploy_manual_prod.sh
```

Detailed remote VPS instructions for the new React frontend + backend are in [DEPLOY_VPS.md](DEPLOY_VPS.md).

Checks:

```bash
docker compose ps
curl -fsS http://localhost:8001/health
docker compose logs -f --tail=200 daqs
```
