# DAQS v4.2: The "Persona-Driven" Architecture
### Neuro-Symbolic Abstract Narrative Engine

DAQS (Dialogue Abstract Quest System) is a hybrid engine where **Logic (PDDL)** defines *what* can happen, and **Persona (YAML + LLM)** defines *how* it happens and *whether* it happens at all.

---

## 1. Core Philosophy: Game as Code (GaC)

Unlike pure LLM chats, DAQS uses a rigid data structure to control the narrative. We do not rely on a model to "understand" context; we **mathematically constrain** its choices via Python filters.

---

## 2. Architecture Layers

### Layer 1: The Skeleton (PDDL Logic)
An abstract state graph shared by all characters.
* `ctx_intro` -> `ctx_deep` -> `ctx_core`
* Actions: `shift-context`, `activate-trigger`, `deploy-paradox`.

### Layer 2: The Skin (Persona Overrides)
Each character is a "cartridge" that overrides world perception.
In the persona file (`persona_gnome.yaml`) the `world_overrides` section is used:

```yaml
world_overrides:
  ctx_intro:
    name: "The Stumbling Badger Tavern" # Instead of "Digital Void"
    description: "Smell of ale and roasted pork..."
```
The orchestrator swaps descriptions on the fly while keeping logical IDs for PDDL.

### Layer 3: The Filter (Logic Gating via Tags)
The most important protection mechanism. To avoid hacks and role breaks, we use a tag system.

1. **Entity Tags:** A character has tags (`tags: [fantasy, organic]`).
2. **Trigger Requirements:** A trigger has a requirement (`required_tag: tech`).
3. **Hard Filtering:** Before sending a prompt to the LLM, Python code checks compatibility.
    * *Result:* The gnome **physically cannot see** the option to activate a technical protocol. For NLU this move does not exist.

### Layer 4: The Chain (Dependency Gating)
Triggers can depend on items.
* `requires: cpt_trust` — you cannot ask about a secret until trust is gained.
* `requires: cpt_axiom` — you cannot create a paradox until you know the axiom.

---

## 3. The Subjective NLU

Even if a move passes the filters, NLU analyzes it through the persona's perception. The NLU prompt contains an **NPC PERSPECTIVE** block:
> "You should be completely immersed in the NPC role... analyze the user input from the NPC point of view."

This lets the system catch nuances:
* "Hi?" for a Robot -> `Ping` (Protocol Initiation).
* "Hi?" for a Gnome -> `Mumble` (Noise).

---

## 4. Technical Stack
* **Orchestrator:** Python class that assembles prompts and manages `reload()` of data.
* **WebUI (Streamlit):** Interface with Hot-Swapping (persona switching on the fly).
* **Gemini 1.5/2.0:** Primary LLM engine.

### How to Run
```bash
streamlit run social_webui.py
```
