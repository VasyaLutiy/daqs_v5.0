# DAQS v4.0: Enterprise PDDL Orchestrator Manual

## 1. Introduction
In v4.0 the architecture shifts from rigid dialogue trees to **declarative personas**. Instead of scripting every dialogue step, we describe the “physics” of a character and their secrets.

## 2. Key Components

### 2.1 Universal Domain (`universal_domain.pddl`)
Contains shared social interaction rules for all NPCs:
- **Red Lines**: Predicate `is-hostile`. When true, most actions are blocked.
- **Leverage**: Predicate `has-item`. Secrets are revealed only when the player holds the right items.
- **Goal**: Predicate `secret-revealed`.

### 2.2 Persona Atlas
YAML file describing a specific NPC.
- **Traits**: List of traits (greedy, paranoid, etc.) that shape LLM response style.
- **Secrets**: List of goals the player can reach and the conditions to unlock them.
- **Red Lines**: Triggers that switch the NPC into `hostile`.

## 3. Workflow

### Step 1: Describe the character
Create a file in `npc_engine/config/social_world/nodes/personas/`. Describe their secrets and key items. No dialogue code needed.

### Step 2: Initialize the session
The engine loads the universal domain and injects persona YAML data into it, forming a PDDL problem.

### Step 3: Interaction loop
1. **Input**: Player enters text.
2. **NLU**: LLM classifies the player’s intent into PDDL terms (e.g., `cross-red-line` or `reveal-secret`).
3. **Validation**: The PDDL engine checks whether the action is allowed (e.g., does the player have the item).
4. **State Update**: If allowed, the simulator updates the world state.
5. **Generation**: The LLM replies with the current list of valid PDDL actions and persona status in its prompt.

## 4. Hallucination Guardrails
In v4.0 the model is constrained by a **Valid Moves list**. If the planner does not include `reveal-secret` in the valid moves, the LLM is hard-forbidden (in the system prompt) from revealing any important info.

## 5. Analytics and Simulation
Use `UPSequentialSimulator` for:
- Predicting player type (Aggressor/Explorer) early.
- Auto-hinting if the player strays from the optimal path to a secret.

---
*DAQS Enterprise Engine Documentation v4.0*
