(define (domain narrative-flow)
  (:requirements :strips :typing :negative-preconditions)

  (:types
    agent
    context      
    concept      
    trigger      
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
    (requires-combo ?target - context ?c1 - concept ?c2 - concept) ; New!
  )

  ; --- ACTIONS ---

  (:action shift-context
    :parameters (?a - agent ?from - context ?to - context)
    :precondition (and 
        (active-context ?a ?from)
        (connected ?from ?to)
        (not (locked ?to))
    )
    :effect (and 
        (not (active-context ?a ?from))
        (active-context ?a ?to)
        (visited ?to)
    )
  )

  (:action learn-concept
    :parameters (?a - agent ?ctx - context ?conc - concept)
    :precondition (and 
        (active-context ?a ?ctx)
        (provides-concept ?ctx ?conc)
        (not (has-concept ?a ?conc))
    )
    :effect (and 
        (has-concept ?a ?conc)
    )
  )

  (:action activate-trigger
    :parameters (?a - agent ?ctx - context ?trig - trigger ?conc - concept)
    :precondition (and 
        (active-context ?a ?ctx)
        (in-context ?trig ?ctx)
        (trigger-yields ?trig ?conc)
        (not (exhausted ?trig))
    )
    :effect (and 
        (exhausted ?trig)
        (has-concept ?a ?conc)
    )
  )

  (:action apply-concept
    :parameters (?a - agent ?current - context ?target - context ?key - concept)
    :precondition (and 
        (active-context ?a ?current)
        (connected ?current ?target)
        (locked ?target)
        (requires-concept ?target ?key)
        (has-concept ?a ?key)
    )
    :effect (and 
        (not (locked ?target))
    )
  )

  ; NEW: Logical Bomb
  (:action deploy-paradox
    :parameters (?a - agent ?current - context ?target - context ?c1 - concept ?c2 - concept)
    :precondition (and 
        (active-context ?a ?current)
        (connected ?current ?target)
        (locked ?target)
        (requires-combo ?target ?c1 ?c2)
        (has-concept ?a ?c1)
        (has-concept ?a ?c2)
    )
    :effect (and 
        (not (locked ?target))
        ; We could force move or just unlock. Let's just unlock for consistency.
    )
  )
)