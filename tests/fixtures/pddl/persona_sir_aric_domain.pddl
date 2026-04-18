(define (domain narrative-flow)
  (:requirements :strips :typing :negative-preconditions :adl)

  (:types
    agent
    context      
    concept      
    trigger
    item
    mood
    tag
    action-id
  )

  (:constants
    id_act_armor_clank - action-id
    id_act_holy_salute - action-id
    id_act_sun_blade_glow - action-id
    armor - tag
    blade - tag
    heavy - tag
    helmet - tag
    holy - tag
    radiant - tag
    neutral - mood
    resolute - mood
    righteous - mood
  )

  (:predicates
    ; --- Navigation ---
    (active-context ?a - agent ?c - context)  
    (connected ?from - context ?to - context) 
    
    ; --- State ---
    (visited ?c - context)                    
    (locked ?c - context)                     
    (exhausted ?t - trigger)                  

    ; --- Inventory ---
    (has-concept ?a - agent ?c - concept)     
    
    ; --- World Logic ---
    (provides-concept ?c - context ?conc - concept)   
    (trigger-yields ?t - trigger ?conc - concept)     
    (in-context ?t - trigger ?c - context)            
    
    (requires-concept ?target - context ?req - concept) 
    (requires-combo ?target - context ?c1 - concept ?c2 - concept)

    ; --- V2 Dynamic Behavior ---
    (current-mood ?a - agent ?m - mood)
    (wearing ?a - agent ?i - item)
    (holding ?a - agent ?i - item)
    (has-tag ?i - item ?t - tag)
    (is-tag ?t1 - tag ?t2 - tag)
    (visual-event-triggered ?action_id - action-id)
  )

  ; --- ACTIONS ---

  (:action shift-context
    :parameters (?a - agent ?from - context ?to - context)
    :precondition (and (active-context ?a ?from) (connected ?from ?to) (not (locked ?to)))
    :effect (and (not (active-context ?a ?from)) (active-context ?a ?to) (visited ?to))
  )

  (:action learn-concept
    :parameters (?a - agent ?ctx - context ?conc - concept)
    :precondition (and (active-context ?a ?ctx) (provides-concept ?ctx ?conc) (not (has-concept ?a ?conc)))
    :effect (and (has-concept ?a ?conc))
  )

  (:action activate-trigger
    :parameters (?a - agent ?ctx - context ?trig - trigger ?conc - concept)
    :precondition (and (active-context ?a ?ctx) (in-context ?trig ?ctx) (trigger-yields ?trig ?conc) (not (exhausted ?trig)))
    :effect (and (exhausted ?trig) (has-concept ?a ?conc))
  )

  (:action apply-concept
    :parameters (?a - agent ?current - context ?target - context ?key - concept)
    :precondition (and (active-context ?a ?current) (connected ?current ?target) (locked ?target) (requires-concept ?target ?key) (has-concept ?a ?key))
    :effect (and (not (locked ?target)))
  )

  (:action apply-combo-concept
    :parameters (?a - agent ?current - context ?target - context ?c1 - concept ?c2 - concept)
    :precondition (and 
        (active-context ?a ?current) 
        (connected ?current ?target) 
        (locked ?target) 
        (requires-combo ?target ?c1 ?c2) 
        (has-concept ?a ?c1)
        (has-concept ?a ?c2)
    )
    :effect (and (not (locked ?target)))
  )

  ; --- DYNAMIC BEHAVIOR GENERATION ---
  (:action do_act_holy_salute
      :parameters (?a - agent ?item_h - item ?tag_h - tag
      )
      :precondition (and 
          (current-mood ?a neutral)
          (holding ?a ?item_h)
          (has-tag ?item_h ?tag_h)
          (is-tag ?tag_h holy)
      )
      :effect (and 
          (visual-event-triggered id_act_holy_salute)
      )
  )
  (:action do_act_sun_blade_glow
      :parameters (?a - agent ?item_h - item ?tag_h - tag
      )
      :precondition (and 
          (current-mood ?a righteous)
          (holding ?a ?item_h)
          (has-tag ?item_h ?tag_h)
          (is-tag ?tag_h holy)
      )
      :effect (and 
          (visual-event-triggered id_act_sun_blade_glow)
      )
  )
  (:action do_act_armor_clank
      :parameters (?a - agent ?item_w - item ?tag_w - tag
      )
      :precondition (and 
          (current-mood ?a resolute)
          (wearing ?a ?item_w)
          (has-tag ?item_w ?tag_w)
          (is-tag ?tag_w armor)
      )
      :effect (and 
          (visual-event-triggered id_act_armor_clank)
      )
  )
)
