# DAQS v5.0: The Unified Neuro-Symbolic Engine

**DAQS (Deterministic Adaptive Quest System)** is a hybrid game engine that combines deterministic planning logic (PDDL) with LLM creativity.

Version 5.0 merges physical world navigation (World Engine) and deep social character logic (Social Engine) into one seamless experience.

## About the project
We built DAQS for the Gemini hackathon to bridge a gap we kept seeing: rigid scripted NPCs feel fake, while free-form LLM NPCs hallucinate, forget inventory, and break quest chains. DAQS pairs Gemini for natural language with a PDDL planner for provable game logic, so characters improvise while every move is mathematically grounded.

### Inspiration
Modern AI NPCs talk well but act poorly. Inspired by GOAP systems (F.E.A.R., S.T.A.L.K.E.R.) and Gemini’s multimodal stack, we asked: what if NPCs spoke with Gemini but thought with a planner? That “two-brain” idea—LLM for style, PDDL for truth—became DAQS.

### How we built it
- **Neuro-symbolic core:** We model each session as a PDDL tuple \\(\\Pi = \\langle O, I, G \\rangle\\) where operators \\(O\\) cover moves like `move`, `pickup`, `persuade`, \\(I\\) is the live state (location, inventory, mood), and \\(G\\) encodes quest goals. Plans \\(\\pi = \\langle a_1, a_2, \\dots, a_k \\rangle\\) come from unified_planning/Fast Downward.
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

### 1. Launch the logic server (Backend)
```bash
cd npc_engine
uvicorn main_fast:app --host 0.0.0.0 --port 8000
```

### 2. Launch the interface (Frontend)
```bash
# From the repo root
streamlit run social_webui.py
```

## 🛠 Key Features in v5.0
* **The Oracle Prologue**: NPC auto-generates a quest prophecy by analyzing the PDDL graph.
* **Mini-Map**: Live visualization of the location graph with fog of war.
* **Auto-Enter Logic**: Seamless entry into new contexts when they unlock.
* **Persistence**: Auto-saving player state to `player_state.json`.
* **Global Triggers**: Ability to discuss core topics (Axioms) in any location.

## 📂 Project Structure
* `gamemaster/`: Social engine logic, prompts, and orchestrator.
* `npc_engine/`: World engine logic, FastAPI server, and PDDL generators.
* `social_webui.py`: Single Streamlit dashboard.
* `player_state.json`: Current game save.

---
Developed by VasyaLutiy & AI Architect.
