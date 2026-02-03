# PERSONA ATLAS MANUAL
## Creating Dialogue Personas for DAQS Social Engine

This manual provides comprehensive guidance for creating dialogue personas in the DAQS (Dialogue And Quest System) social engine. Personas define NPC behavior, dialogue trees, and interaction patterns.

---

## Table of Contents

1. [Persona Architecture Overview](#persona-architecture-overview)
2. [Basic Persona Structure](#basic-persona-structure)
3. [Tags System](#tags-system)
4. [Contexts and Dialogue Flow](#contexts-and-dialogue-flow)
5. [Triggers and Interactions](#triggers-and-interactions)
6. [Properties and Configuration](#properties-and-configuration)
7. [Persona Types and Examples](#persona-types-and-examples)
8. [Best Practices](#best-practices)
9. [Testing and Validation](#testing-and-validation)
10. [Declarative Personalities (v4.0)](#declarative-personalities-v40)

---

## Persona Architecture Overview

### Core Components

The persona system consists of four main components:

1. **Personas**: Individual NPC definitions with personality traits
2. **Contexts**: Dialogue states and conversation scenes
3. **Triggers**: Player actions and NPC responses
4. **Tags**: Behavior modifiers and personality flags

### File Structure

```
npc_engine/config/social_world/nodes/personas/
├── atlas_name.yaml          # Persona group definition
├── individual_persona.yaml  # Single persona (legacy)
```

### Processing Flow

1. **Initialization**: Persona loaded from YAML
2. **Context Selection**: Based on player state and tags
3. **Trigger Evaluation**: Player actions checked against conditions
4. **Response Generation**: LLM generates dialogue based on context
5. **State Updates**: Concepts and progress tracked

---

## Basic Persona Structure

### Persona Group Format (Recommended)

```yaml
id: atlas_elves
type: persona_group
description: "Denizens of the ancient woods and elven mercenaries."

personas:
  - id: persona_dolores
    type: persona
    name: "Dolores the Cynic"
    description: "An elven mercenary who values skill and profit over ideals."
    tags: ["proactive", "mercenary", "business-oriented"]
    properties:
      dialogue_hook: "analyze_quest_difficulty"
      target_social_goal: "ctx_joined"
    world_overrides:
      ctx_tavern_intro:
        is_start: true

    # Nested definitions
    contexts: [...]
    triggers: [...]
```

### Individual Persona Format (Legacy)

```yaml
id: persona_cyber
type: persona
name: "Cyber Punk"
description: "A street-smart hacker with attitude."
tags: ["neutral", "technical"]
contexts: [...]
triggers: [...]
```

---

## Tags System

Tags control NPC behavior and determine available actions. They are checked by the game engine to enable/disable specific features.

### Core Tag Categories

#### Initiative Tags
- `proactive` - NPC can initiate conversations, offers, and flirts
- `reactive` - NPC only responds to player actions
- `neutral` - NPC maintains professional distance

#### Personality Tags
- `mercenary` - Business-focused, profit-driven
- `romantic` - Can engage in flirtatious behavior
- `aggressive` - Hostile or confrontational
- `helpful` - Assists player willingly
- `mysterious` - Gives cryptic or incomplete information

#### Role Tags
- `quest-giver` - Can provide quests and missions
- `merchant` - Sells items and services
- `informant` - Provides lore and information
- `companion` - Can join player party

### Tag Usage in Engine

```python
# Example: Proactive mercenary behavior
if "proactive" in persona_tags and "mercenary" in persona_tags:
    # Enable partnership offers
    offers.append(f"npc-offer player {context} {trigger} {concept}")

# Example: Romantic personality
if "romantic" in persona_tags and "proactive" in persona_tags:
    # Enable flirting
    flirts.append(f"npc-flirt player {context} {trigger} {concept}")
```

---

## Contexts and Dialogue Flow

Contexts define conversation states and control dialogue progression.

### Context Structure

```yaml
contexts:
  - id: ctx_tavern_intro
    type: context
    name: "Dolores' Gaze"
    description: "Dolores watches you from the corner booth. Her eyes scan your equipment, calculating your worth."
    connections:
      - to: ctx_neutral_talk
        direction: forward
      - to: ctx_mockery
        direction: forward
      - to: ctx_partnership
        direction: forward
    properties:
      is_start: true
```

### Context Properties

#### Basic Properties
- `is_start: true` - Entry point for conversations
- `is_locked: true` - Requires specific conditions to access
- `required_concept: cpt_quest_hard` - Concept needed to unlock

#### Advanced Properties
- `provides_concept: cpt_location_known` - Concept granted on entry
- `unlock_actions: [...]` - Complex unlock requirements
- `is_global: true` - Available from any context

### Connection Directions

- `forward` - Progress conversation (player initiative)
- `backward` - Return to previous state
- `branch` - Alternative path based on choices

### Context Flow Patterns

#### Linear Conversation
```
Start → Greeting → Business → Agreement → End
```

#### Branching Dialogue
```
Start → Greeting
    ├── Polite → Business → Agreement
    └── Rude → Conflict → Rejection
```

#### Circular Conversation
```
Start → Small Talk → Business → Back to Start
```

---

## Triggers and Interactions

Triggers define player actions and NPC responses within contexts.

### Trigger Structure

```yaml
triggers:
  - id: trig_accept_partnership
    type: trigger
    name: "Accept Offer"
    description: "Agree to her terms and form an alliance."
    parent_context: ctx_partnership
    requires: cpt_partnership_offer  # Optional condition
    yields: cpt_agreement
    properties:
      is_unique: true  # Can only be used once
```

### Trigger Types

#### Standard Triggers
- `activate-trigger` - Player activates specific action
- `npc-offer` - NPC initiates offer (partnership, trade, etc.)
- `npc-flirt` - NPC initiates romantic advance

#### Special Triggers
- `learn-concept` - Player gains knowledge
- `apply-concept` - Unlock new contexts or abilities
- `shift-context` - Change conversation state

### Trigger Conditions

#### Concept Requirements
```yaml
requires: cpt_gold_coins  # Must have this concept
required_tag: merchant    # Persona must have this tag
```

#### Context Restrictions
```yaml
parent_context: ctx_tavern_intro  # Only available in this context
global: true                      # Available in all contexts
```

### Trigger Chains

Create complex interaction sequences:

```yaml
# Initial offer
- id: trig_offer_quest
  yields: cpt_quest_available

# Acceptance
- id: trig_accept_quest
  requires: cpt_quest_available
  yields: cpt_quest_active

# Completion
- id: trig_complete_quest
  requires: cpt_quest_active
  yields: cpt_quest_complete
```

---

## Properties and Configuration

### Persona Properties

```yaml
properties:
  dialogue_hook: "analyze_quest_difficulty"  # Function for quest analysis
  target_social_goal: "ctx_joined"           # Final objective context
  personality_traits: ["cynical", "sharp"]   # Descriptive traits
  relationship_start: "neutral"              # Initial disposition
```

### World Overrides

Modify global contexts for specific personas:

```yaml
world_overrides:
  ctx_tavern_intro:
    is_start: true              # This persona starts here
    description: "Custom description for this NPC"
  ctx_forest_clearing:
    is_locked: false           # Override global lock
```

### Dialogue Hooks

Functions called during conversation processing:

- `analyze_quest_difficulty` - Assess quest complexity
- `calculate_relationship` - Update NPC disposition
- `generate_response` - Custom dialogue generation

---

## Persona Types and Examples

### 1. Mercenary (Dolores)

**Tags**: `["proactive", "mercenary", "business-oriented"]`

**Behavior**: Offers partnerships for profit, flirts conditionally, values capability over ideals.

```yaml
contexts:
  - id: ctx_partnership
    name: "Business Proposition"
    description: "NPC sets down glass. 'You're heading to the Fort. Suicide... unless you have a sharpshooter.'"
```

### 2. Romantic Interest

**Tags**: `["proactive", "romantic", "helpful"]`

**Behavior**: Flirts frequently, offers emotional support, prioritizes relationships over business.

### 3. Quest Giver

**Tags**: `["reactive", "helpful", "quest-giver"]`

**Behavior**: Provides quests when asked, gives lore, assists with information.

### 4. Merchant

**Tags**: `["reactive", "merchant", "neutral"]`

**Behavior**: Sells items, barters, provides services for payment.

### 5. Antagonist

**Tags**: `["proactive", "aggressive", "mysterious"]`

**Behavior**: Creates obstacles, provides false information, opposes player goals.

---

## Best Practices

### Dialogue Design

#### Natural Flow
- Use varied sentence lengths
- Include personality-specific idioms
- Create branching conversations
- Avoid repetitive responses

#### Context Awareness
- Reference player actions and choices
- Remember previous conversations
- Adapt tone based on relationship
- Use appropriate formality levels

### Technical Guidelines

#### ID Naming Convention
```
persona_[name]           # Persona identifier
ctx_[location]_[state]   # Context identifier
trig_[action]_[result]   # Trigger identifier
cpt_[category]_[item]    # Concept identifier
```

#### Concept Management
- Use specific, descriptive concept names
- Avoid generic concepts like "cpt_good"
- Chain concepts for complex requirements
- Document concept purposes

#### Performance Considerations
- Limit context connections (max 5-7 per context)
- Use concept requirements to control flow
- Avoid circular dependencies
- Test with multiple conversation paths

### Testing Checklist

#### Functionality
- [ ] All contexts reachable
- [ ] Triggers fire correctly
- [ ] Concepts granted properly
- [ ] Dialogue generates appropriately

#### User Experience
- [ ] Natural conversation flow
- [ ] Clear player choices
- [ ] Appropriate NPC personality
- [ ] No dead-end conversations

#### Edge Cases
- [ ] Player with no quest
- [ ] Player with completed quests
- [ ] Multiple conversation attempts
- [ ] Context state persistence

---

## Testing and Validation

### Manual Testing

1. **Conversation Flow**
   - Start conversation
   - Try all dialogue branches
   - Verify context transitions
   - Check concept acquisition

2. **NPC Behavior**
   - Test with different player states
   - Verify tag-based behavior
   - Check offer/flirt conditions
   - Validate personality consistency

3. **Integration Testing**
   - Test with quest system
   - Verify world state integration
   - Check save/load functionality
   - Validate multiplayer compatibility

### Automated Testing

```python
def test_persona_dolores():
    # Test mercenary behavior
    state = create_test_state(has_quest=True)
    offers = engine._get_npc_offers(state, [], ["proactive", "mercenary"])
    assert "npc-offer" in offers[0]

def test_context_transitions():
    # Test dialogue flow
    assert can_reach_context("ctx_partnership", "ctx_tavern_intro")
    assert context_requires_concept("ctx_joined", "cpt_agreement")
```

### Validation Tools

#### Debug Commands
- `show_contexts` - Display all contexts
- `show_triggers` - List available triggers
- `show_concepts` - Current player concepts
- `test_dialogue` - Simulate conversation

#### Logging
Enable debug logging to trace:
- Context transitions
- Trigger activations
- Concept changes
- Dialogue generation

---

## Advanced Techniques

### Dynamic Context Generation

Create contexts programmatically based on game state:

```python
def generate_quest_context(quest_data):
    return {
        "id": f"ctx_quest_{quest_data['id']}",
        "name": quest_data['name'],
        "description": quest_data['description'],
        "properties": {
            "is_locked": True,
            "required_concept": f"cpt_quest_{quest_data['id']}_available"
        }
    }
```

### Conditional Dialogue

Use context properties for dynamic responses:

```yaml
contexts:
  - id: ctx_mood_based
    name: "Variable Response"
    description: "NPC responds based on relationship"
    properties:
      dialogue_variants:
        friendly: "Welcome back, friend!"
        neutral: "What do you want?"
        hostile: "Make it quick."
```

### Multi-Persona Interactions

Create interconnected persona groups:

```yaml
# Group definition
personas:
  - id: persona_leader
    tags: ["proactive", "authoritative"]
  - id: persona_follower
    tags: ["reactive", "loyal"]
    properties:
      follows: "persona_leader"
```

---

## Troubleshooting

### Common Issues

#### Context Not Unlocking
- Check required concepts are granted
- Verify concept names match exactly
- Ensure trigger yields correct concept

#### Triggers Not Firing
- Confirm parent_context is correct
- Check requires conditions are met
- Verify trigger ID is referenced properly

#### Dialogue Loops
- Avoid circular context connections
- Add escape triggers to return to safe contexts
- Use concept requirements to prevent repetition

#### Performance Issues
- Limit total contexts per persona (<20)
- Use concept caching for frequent checks
- Avoid complex trigger conditions

### Debug Process

1. Enable logging: `logger.setLevel(DEBUG)`
2. Check context state: Current context and concepts
3. Verify trigger conditions: Required concepts present
4. Test dialogue generation: LLM receives correct context
5. Validate state updates: Concepts granted, context changed

---

## Migration Guide

### From Legacy Format

Convert individual persona files to atlas format:

```bash
# Old structure
personas/
├── persona_a.yaml
├── persona_b.yaml

# New structure
personas/
├── atlas_faction_a.yaml  # Contains persona_a, persona_b
├── atlas_faction_b.yaml  # Contains persona_c, persona_d
```

### Tag Migration

Update hardcoded logic to use tags:

```python
# Old: Hardcoded check
if persona_id == "persona_dolores":
    # Dolores-specific logic

# New: Tag-based logic
if "mercenary" in persona_tags:
    # Mercenary behavior for any persona
```

### Context Migration

Move nested contexts to persona definitions:

```yaml
# Old: Separate context files
# New: Nested in persona
personas:
  - id: persona_name
    contexts:
      - id: ctx_custom_context
        # ... context definition
```

---

## Declarative Personalities (v4.0)

Version 4.0 introduces an Enterprise-grade approach where personas are defined by **Traits** and **Secrets** rather than explicit dialogue trees.

### V4 Persona Structure

```yaml
id: persona_dolores
type: persona_v4
traits:
  - id: trait_cynical
    desc: "Cynical worldview, doesn't trust easily."
  - id: trait_greedy
    desc: "Motivated by money and rare items."

secrets:
  - id: secret_shadow_deal
    requires_item: item_shadow_coin
    description: "Location of the smuggling route."

red_lines:
  - trigger: "physical_threat"
    action: "cross-red-line"
    response: "NPC becomes hostile forever."
```

### Key Differences from v2
1. **Universal Domain**: All NPCs share one `universal_domain.pddl`.
2. **Dynamic Generation**: The engine injects PDDL state (hostility, leverage) directly into LLM prompts.
3. **Implicit Goals**: Success is defined by reaching the `secret-revealed` PDDL state.

---

*This manual is maintained alongside the DAQS codebase. For the latest updates and examples, check the repository documentation.*</content>
<parameter name="filePath">/home/john/Documents/Work2026/pddl_projects/daqs/v_2.0/PERSONA_ATLAS_MANUAL.md