# DAQS v5.0: The Dialogue & Quest Architecture Manual

**"Neuro-Symbolic NPCs are not scripted. They are simulated."**

This manual describes the V5.0 architecture used to create dynamic, context-aware NPCs like *Megan the Mystic*, *Lok'tar the Orc*, and *Sir Aric*. It covers the entire pipeline: from YAML definition to PDDL generation and LLM narrative rendering.

---

## 1. The Core Concept: Atlas System

In DAQS v5.0, characters are not defined in isolation. They are grouped into **Atlases** (e.g., `atlas_elves.yaml`, `atlas_paladins.yaml`).

### File Structure
All social definitions live in:
`npc_engine/config/social_world/nodes/personas/`

### Anatomy of an Atlas (`type: persona_group`)

An Atlas is a container that holds:
1.  **Global Concepts**: Shared knowledge tokens (e.g., `cpt_respect`, `cpt_quest_hard`) accessible to all personas in this group.
2.  **Personas**: List of distinct personalities (e.g., Dolores, Megan).
3.  **Nested World**: Contexts and Triggers specific to these personas.

---

## 2. Defining a Persona (The Soul)

A Persona is the "software" that runs inside an NPC. It defines *who* they are and *what* they can do.

```yaml
  - id: persona_sir_aric
    type: persona
    name: "Sir Aric"
    description: "A stoic paladin..."
    
    # --- CONTROL PROPERTIES ---
    properties:
      target_social_goal: "ctx_aric_blessing" # The 'Endgame' of the conversation
      behavior_on_enter: "active"             # active = speaks first; passive = waits for player
      perform_quest_analysis: true            # true = analyzes player's quest difficulty on entry
      use_dynamic_generation: true            # true = enables V2 PDDL architecture
      oracle_interpretation: "a blinding flash of divine light" # How they 'see' the future in the Prologue
    
    # --- DYNAMIC BEHAVIOR (V2) ---
    equipment:
      weapons:
        - id: item_sun_blade
          name: "Sun Blade"
          pddl_tags: ["holy", "blade"] # Used by Planner
    
    behavior_rules:
      - id: act_divine_glow
        mood: righteous  # Only available in this mood
        requires_holding_tag: holy
        narrative_template: "raises his {item_name}, radiating blinding light"
```

---

## 3. Binding to the World (The Body)

To make a Persona appear in the game, you must bind it to a physical NPC entity in a Region file (e.g., `enchanted_forest.yaml`).

**Location Definition:**
```yaml
- id: tavern
  type: location
  ...
  contains:
    npcs:
    - id: npc_megan
      type: npc                  # Physical Entity Type
      name: "Megan"
      social_persona: persona_megan  # <--- THE BINDING LINK
      properties:
          has_items: ["item_crystal_staff"] # Physical Inventory (syncs with Social Equipment)
```

**Crucial:** The `social_persona` field tells the WebUI which YAML definition to load when the player clicks "Talk".

---

## 4. The Flow of Conversation

The dialogue is a **State Machine** driven by PDDL logic. It is NOT a tree. It is a Graph.

### Contexts & Moods
Contexts are "Mental States". Moving between contexts can change the NPC's mood.

```yaml
    contexts:
      - id: ctx_aric_righteous
        name: "Divine Judgment"
        properties:
          is_locked: false
          induces_mood: "righteous" # <--- Switches mood on entry!
```

### Automatic Quest Analysis
If `perform_quest_analysis: true`, the system executes a PDDL hook before the conversation starts:
1.  Analyzes the player's active quest goal.
2.  Calculates complexity (Plan Length).
3.  Injects a concept: `cpt_quest_easy`, `cpt_quest_hard`, or `cpt_quest_none`.
4.  **Result:** The NPC automatically knows if you are a newbie or a veteran.

---

## 5. Under the Hood: How it Works

### A. The Cache Manager
*   **Role**: Loads all YAMLs into a giant dictionary.
*   **Feature**: It merges "Atlas Concepts" into "Persona Concepts", so `persona_aric` can see `cpt_respect` defined in the atlas root.

### B. PDDL Orchestrator (The Brain)
*   **Role**: Generates a unique PDDL Domain for *this specific interaction*.
*   **Dynamic Logic**: It loops through `behavior_rules` and creates PDDL actions (`:action do_act_divine_glow`).
*   **State Injection**: It injects `(current-mood player righteous)` and `(holding player item_sun_blade)` into the Problem file.

### C. Move Validator (The Referee)
*   **Role**: Asks: "What can the NPC do right now?"
*   **V2 Logic**: It checks `behavior_rules`. If Mood == Righteous AND Weapon == Holy, it adds `do_act_divine_glow` to the list of Valid Moves.

### D. Prompt Orchestrator (The Narrator)
*   **Role**: Translates PDDL codes back into English.
*   **Translation**: Converts `do_act_divine_glow` -> "raises his Sun Blade..."
*   **Assembly**: Builds the final System Prompt, injecting `NPC Mood`, `Physical Location` (from World Engine), and the `Visual Event`.

---

## 6. How to Create a "Mission Board" NPC

To make an NPC give quests immediately (like Sir Aric):

1.  **Override the Start**: Set `is_start: true` on `ctx_quest_offer`.
2.  **Define the Context**:
    ```yaml
      - id: ctx_quest_offer
        type: context
        name: "War Room"
        description: "Aric points to the map. 'Here are the targets.'"
        properties:
          is_start: true # Skip the "Hello" phase
    ```
3.  **The UI Magic**: The WebUI automatically detects `ctx_quest_offer` and renders the **Mission Board Buttons** instead of the chat input.

---

## 7. Quick CLI Checks (MoveValidator)

Two handy one-liners to validate persona graphs without opening the UI. Run from repo root; adjust `persona`, `ctx`, `mood` as needed.

**Valid moves for a persona/context/mood**
```bash
~/Documents/python_venv/venv312/bin/python3 - <<'PY'
from npc_engine.engine.gamemaster.cache_manager import CacheManager
from npc_engine.engine.gamemaster.move_validator import MoveValidator
from pathlib import Path
persona = "persona_sir_aric"; ctx = "ctx_aric_quest_offer"; mood = "neutral"
cache = CacheManager(Path("npc_engine/config")).cache
mv = MoveValidator(cache)
state = {"current_context": ctx, "concepts": [], "unlocked_contexts": [], "active_persona": persona, "current_mood": mood}
print(f"Persona={persona}, ctx={ctx}, mood={mood}")
for m in mv.get_valid_moves(state):
    print(" ", m)
PY
```

**Quick dump of persona contexts + connections (+mood locks)**
```bash
~/Documents/python_venv/venv312/bin/python3 - <<'PY'
from npc_engine.engine.gamemaster.cache_manager import CacheManager
from pathlib import Path
persona = "persona_sir_aric"
cache = CacheManager(Path("npc_engine/config")).cache
p = cache["personas"][persona]
print(f"Contexts for {persona}:")
for c in p.get("contexts", []):
    cid = c["id"]; conns = ", ".join(f"{conn['direction']} -> {conn['to']}" for conn in c.get("connections", []))
    mood = c.get("properties", {}).get("induces_mood")
    lock = c.get("properties", {}).get("is_locked")
    extra = []
    if mood: extra.append(f"mood={mood}")
    if lock: extra.append("locked")
    print(f"- {cid}: {conns or 'no connections'}" + (f" ({', '.join(extra)})" if extra else ""))
PY
```

---

## 7. Troubleshooting

*   **"Attempted to execute unknown hook"**: You forgot to import `quest_hooks` in the frontend code.
*   **"Found invalid expression: cpt_..."**: The concept is used in a transition but not defined in the `concepts` list of the Atlas or Persona.
*   **NPC sends 3 messages at once**: `npc_behavior.py` lacks priority logic. (Fixed in v5.6).
*   **"Unknown Location"**: `handle_npc_interaction` didn't update `current_location` in the session state. (Fixed in v5.6).

---
*Created for DAQS v5.0 Architecture.*
