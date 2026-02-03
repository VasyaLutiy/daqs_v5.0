(define (domain exploration)
  (:requirements :strips :typing)

  (:types
    region location item npc - object
  )

  (:predicates
    (at ?obj - object ?l - location)
    (has-item ?p - object ?i - item)
    (path ?l1 - location ?l2 - location)
    (path_available ?l1 - location ?l2 - location)
    (blocked ?l1 - location ?l2 - location ?i - item)
    (accessible ?l - location)
    (controllable ?p - object)
    
    ;; Object-Oriented Portal Logic
    (portal_link ?portal - object ?to - location)
    (portal_key ?portal - object ?key - item)
  )

  (:action move
    :parameters (?p - object ?from - location ?to - location)
    :precondition (and 
        (controllable ?p) 
        (at ?p ?from) 
        (path ?from ?to) 
        (path_available ?from ?to) 
        (accessible ?to)
    )
    :effect (and 
        (at ?p ?to) 
        (not (at ?p ?from))
    )
  )

  (:action pickup
    :parameters (?p - object ?i - item ?l - location)
    :precondition (and 
        (controllable ?p) 
        (at ?p ?l) 
        (at ?i ?l)
    )
    :effect (and 
        (has-item ?p ?i) 
        (not (at ?i ?l))
    )
  )

  (:action unlock
    :parameters (?p - object ?l1 - location ?l2 - location ?i - item)
    :precondition (and 
        (controllable ?p) 
        (at ?p ?l1) 
        (blocked ?l1 ?l2 ?i) 
        (has-item ?p ?i)
    )
    :effect (and 
        (not (blocked ?l1 ?l2 ?i)) 
        (path_available ?l1 ?l2) 
        (accessible ?l2)
    )
  )

  ;; NEW: Teleportation via Portal Object
  (:action teleport
    :parameters (?p - object ?portal - object ?from - location ?to - location ?key - item)
    :precondition (and 
        (controllable ?p) 
        (at ?p ?from) 
        (at ?portal ?from)
        (portal_link ?portal ?to)
        (portal_key ?portal ?key)
        (has-item ?p ?key)
    )
    :effect (and 
        (at ?p ?to) 
        (not (at ?p ?from))
        (accessible ?to)
    )
  )
)