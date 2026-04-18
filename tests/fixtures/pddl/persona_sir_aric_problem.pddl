
(define (problem narrative-journey)
  (:domain narrative-flow)
  (:objects
ctx_aric_quest_offer - context
ctx_aric_intro - context
ctx_aric_duty - context
ctx_aric_righteous - context
ctx_aric_blessing - context
cpt_respect - concept
cpt_quest_none - concept
cpt_quest_easy - concept
cpt_quest_hard - concept
player_001 - agent
persona_sir_aric - agent
item_silver_plate - item
item_aric_helmet - item
item_sun_blade - item

  )
  (:init
(active-context player_001 ctx_aric_quest_offer)
(connected ctx_aric_duty ctx_aric_intro)
(connected ctx_aric_intro ctx_aric_duty)
(connected ctx_aric_intro ctx_aric_righteous)
(connected ctx_aric_quest_offer ctx_aric_duty)
(connected ctx_aric_righteous ctx_aric_intro)
(has-tag item_aric_helmet helmet)
(has-tag item_aric_helmet holy)
(has-tag item_silver_plate armor)
(has-tag item_silver_plate heavy)
(has-tag item_sun_blade blade)
(has-tag item_sun_blade holy)
(has-tag item_sun_blade radiant)
(holding player_001 item_sun_blade)
(is-tag armor armor)
(is-tag blade blade)
(is-tag heavy heavy)
(is-tag helmet helmet)
(is-tag holy holy)
(is-tag radiant radiant)
(requires-concept ctx_aric_blessing cpt_respect)
(wearing player_001 item_aric_helmet)
(wearing player_001 item_silver_plate)

  )
  (:goal
    
    (visited ctx_aric_blessing)
    
  )
)
