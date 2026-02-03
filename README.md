# DAQS v5.0: The Unified Neuro-Symbolic Engine

**DAQS (Deterministic Adaptive Quest System)** is a hybrid game engine that combines deterministic planning logic (PDDL) with LLM creativity.

Version 5.0 merges physical world navigation (World Engine) and deep social character logic (Social Engine) into one seamless experience.

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
