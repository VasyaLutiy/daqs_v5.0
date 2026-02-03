# Meta-Awareness NPC Engine (DAQS v4.0)

## Concept
**Meta-Awareness** is an NPC’s ability to track not just the player’s latest line, but the overall session state, progress toward the goal, and the quality of the player’s actions.

In the DAQS engine this is implemented via a hybrid system:
1. **PDDL Simulation**: Mathematical calculation of the optimal path.
2. **Session Tracking**: Analyzing how far the player deviates from that path.
3. **LLM Synthesis**: Turning the analytics into the NPC’s natural speech.

## Technical Implementation

### 1. Deviation Detection (SessionManager)
The `SessionManager` uses `unified_planning.UPSequentialSimulator` to run a parallel world simulation. After each player turn the system compares:
- **Optimal Path (L_opt)**: Minimum number of steps to reach the Goal from the initial state.
- **Current History (L_actual)**: Number of steps the player has actually taken.
- **Status**: If `L_actual > L_opt + Threshold`, the NPC receives a `DEVIATING` signal.

### 2. Player State Types
- **ON_TRACK**: The player is moving efficiently toward the goal. NPC behaves normally.
- **DEVIATING**: The player is looping or exploring inefficient branches. NPC becomes impatient or gives hints.
- **DEAD_END**: The goal is no longer reachable (for example, a critical item is lost). NPC closes the dialogue.

### 3. Feedback (Hint Injection)
Instead of printing system messages, simulation data is injected into the hidden LLM prompt (Grok/Gemini).
**Example hidden instruction:**
> "The player took 10 steps even though the goal is reachable in 3. They are clearly lost. Your mood: Annoyed. Drop a snarky hint about the 'metal' you need."

## Player Behavior Simulation & Analytics (New v4.1)

### “Multiverse” Concept
With `UPSequentialSimulator` we can run **thousands of parallel simulations** of different strategies on the same PDDL graph. This mathematically proves the quality of the narrative design.

### Archetypes and Topology
In tests (`tests/test_branching_paths.py`) we model three archetypes:
1. **The Pro:** Knows the keywords and follows the optimal (Critical) path.
2. **The Wanderer:** Explores, chases “fluff,” and hits soft dead ends (Soft Lock).
3. **The Brute:** Aggressive, tries to break logic, and hits hard dead ends (Hard Lock / Ban).

### How It Works
The simulator takes an Action Trace and applies it to the PDDL state. On each step it records:
* **Location:** Where the player ended up (Shadowy Corner vs Bar Counter).
* **Inventory:** What they acquired (Secret vs Drunk status).
* **Branch Status:** Active, Blocked, or Completed.

## Predictive Player Profiling & Adaptive Design (New v4.2)

### Topology as a Classifier
In DAQS the dialogue graph is a **semantic filter**. Each PDDL transition is tightly bound to a player intent. This lets us classify the player early ($K < N$), well before the finale.

**Discriminant Node Principle:**
* Transition to `ctx_mockery` (Mockery) is only possible through aggression -> Marker: **[Aggressor]**.
* Transition to `ctx_bar_counter` (Bar) is only possible through distraction -> Marker: **[Explorer]**.
* Transition to `ctx_neutral_talk` (Business) is only possible through constructive moves -> Marker: **[Achiever]**.

### Predictive Analytics
The simulator can predict success probability at any step $K$. If on step 2 the player goes into the “Bar” branch, the architect knows the mathematical distance to the goal tripled. The system flags the player as “Lost” before they realize it.

### On-the-fly Adaptation (AI Director)
Knowing the player’s psychotype early, the PDDL engine can dynamically change goal conditions to keep them in flow:
* **Scenario:** Player classified as **[Brute]** (hates fetch quests, prefers pressure).
* **Problem:** Original finale requires `Coin` (search). The player will quit.
* **Adaptation:** On the fly, the system changes the condition to access `ctx_shadow_deal` for this player: instead of `has_item(coin)` it requires `exhausted(trig_intimidate)`.
* **Result:** The player gets content in their style, narrative coherence stays intact (to them it feels like “I bullied the truth out of her”).

---
*Documentation updated January 20, 2026 (version 4.2)*
