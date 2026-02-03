(define (problem narrative-journey)
  (:domain narrative-flow)
  (:objects

    ctx_megan_intro - context

    ctx_megan_angry - context

    ctx_megan_joy - context

    player_001 - agent

    item_star_robe - item

    item_crystal_staff - item

  )
  (:init

    (connected ctx_megan_intro ctx_megan_angry)

    (connected ctx_megan_intro ctx_megan_joy)

    (connected ctx_megan_angry ctx_megan_intro)

    (connected ctx_megan_joy ctx_megan_intro)

    (active-context player_001 ctx_megan_intro)

    (wearing player_001 item_star_robe)

    (has-tag item_star_robe robe)

    (is-tag robe robe)

    (has-tag item_star_robe magic)

    (is-tag magic magic)

    (holding player_001 item_crystal_staff)

    (has-tag item_crystal_staff staff)

    (is-tag staff staff)

    (has-tag item_crystal_staff focus)

    (is-tag focus focus)

    (current-mood player_001 neutral)

  )
  (:goal
    
    (visual-event-triggered id_act_mystic_ponder)
    
  )
)