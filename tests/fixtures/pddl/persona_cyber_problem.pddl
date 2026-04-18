
(define (problem narrative-journey)
  (:domain narrative-flow)
  (:objects
ctx_intro - context
ctx_deep - context
ctx_core - context
ctx_quest_offer - context
cpt_trust - concept
cpt_axiom - concept
cpt_paradox - concept
trig_compliment - trigger
trig_logic - trigger
trig_protocol - trigger
player_001 - agent
persona_cyber - agent

  )
  (:init
(active-context player_001 ctx_intro)
(connected ctx_deep ctx_core)
(connected ctx_intro ctx_deep)
(connected ctx_intro ctx_quest_offer)
(connected ctx_quest_offer ctx_intro)
(in-context trig_compliment ctx_intro)
(in-context trig_logic ctx_deep)
(in-context trig_protocol ctx_intro)
(locked ctx_deep)
(requires-concept ctx_deep cpt_trust)
(trigger-yields trig_compliment cpt_trust)
(trigger-yields trig_logic cpt_paradox)
(trigger-yields trig_protocol cpt_axiom)

  )
  (:goal
    
    (visited ctx_core)
    
  )
)
