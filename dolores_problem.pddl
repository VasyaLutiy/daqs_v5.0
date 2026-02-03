(define (problem narrative-journey)
  (:domain narrative-flow)
  (:objects

    ctx_tavern_intro - context

    ctx_bar_counter - context

    ctx_mockery - context

    ctx_brawl - context

    ctx_apology - context

    ctx_neutral_talk - context

    ctx_shadow_entry - context

    ctx_shadow_deal - context

    ctx_partnership - context

    ctx_joined - context

    cpt_quest_none - concept

    cpt_quest_easy - concept

    cpt_quest_hard - concept

    cpt_partnership_offer - concept

    cpt_dolores_offer - concept

    cpt_dolores_flirt - concept

    cpt_agreement - concept

    cpt_respect - concept

    cpt_shadow_rumor - concept

    cpt_shadow_token - concept

    cpt_forbidden_knowledge - concept

    cpt_drunk - concept

    cpt_banned - concept

    cpt_apology - concept

    cpt_intimidation - concept

    trig_listen_rumors - trigger

    trig_find_coin - trigger

    trig_hire_companion - trigger

    trig_accept_partnership - trigger

    trig_force_rumor - trigger

    trig_demand_coin - trigger

    trig_apologize - trigger

    player_test - agent

    secret_shadow_deal - secret

    persona_dolores - agent

    item_runic_leather - item

    item_shadow_sword - item

    item_soul_dagger - item

  )
  (:init

    (connected ctx_tavern_intro ctx_neutral_talk)

    (connected ctx_tavern_intro ctx_mockery)

    (connected ctx_tavern_intro ctx_bar_counter)

    (provides-concept ctx_bar_counter cpt_drunk)

    (connected ctx_mockery ctx_brawl)

    (connected ctx_mockery ctx_neutral_talk)

    (connected ctx_brawl ctx_apology)

    (provides-concept ctx_brawl cpt_banned)

    (connected ctx_apology ctx_neutral_talk)

    (connected ctx_neutral_talk ctx_tavern_intro)

    (connected ctx_neutral_talk ctx_shadow_entry)

    (connected ctx_neutral_talk ctx_mockery)

    (locked ctx_neutral_talk)

    (requires-concept ctx_neutral_talk cpt_quest_none)

    (connected ctx_shadow_entry ctx_shadow_deal)

    (locked ctx_shadow_entry)

    (requires-combo ctx_shadow_entry cpt_shadow_rumor cpt_shadow_token)

    (provides-concept ctx_shadow_deal cpt_forbidden_knowledge)

    (connected ctx_partnership ctx_joined)

    (locked ctx_partnership)

    (requires-concept ctx_partnership cpt_partnership_offer)

    (locked ctx_joined)

    (requires-concept ctx_joined cpt_agreement)

    (in-context trig_listen_rumors ctx_neutral_talk)

    (trigger-yields trig_listen_rumors cpt_shadow_rumor)

    (in-context trig_find_coin ctx_neutral_talk)

    (trigger-yields trig_find_coin cpt_shadow_token)

    (in-context trig_hire_companion ctx_tavern_intro)

    (trigger-yields trig_hire_companion cpt_partnership_offer)

    (in-context trig_accept_partnership ctx_partnership)

    (trigger-yields trig_accept_partnership cpt_agreement)

    (in-context trig_force_rumor ctx_mockery)

    (trigger-yields trig_force_rumor cpt_shadow_rumor)

    (in-context trig_demand_coin ctx_mockery)

    (trigger-yields trig_demand_coin cpt_shadow_token)

    (in-context trig_apologize ctx_apology)

    (trigger-yields trig_apologize cpt_apology)

    (active-context player_test ctx_tavern_intro)

    (has-concept player_test cpt_quest_none)

    (requires-item secret_shadow_deal item_shadow_coin)

    (wearing player_test item_runic_leather)

    (has-tag item_runic_leather armor)

    (is-tag armor armor)

    (has-tag item_runic_leather light)

    (is-tag light light)

    (holding player_test item_shadow_sword)

    (has-tag item_shadow_sword blade)

    (is-tag blade blade)

    (has-tag item_shadow_sword magical)

    (is-tag magical magical)

    (holding player_test item_soul_dagger)

    (has-tag item_soul_dagger dagger)

    (is-tag dagger dagger)

    (has-tag item_soul_dagger small)

    (is-tag small small)

  )
  (:goal
    
    (visited ctx_shadow_deal)
    
  )
)