(define (domain universal-social)
  (:requirements :strips :typing :negative-preconditions)

  (:types
    agent       ; NPC или Игрок
    secret      ; Тайна, которую можно выведать
    item        ; Предмет (монета, письмо и т.д.)
    trait       ; Черта личности (жадный, трусливый)
  )

  (:predicates
    (trusts ?npc - agent ?player - agent)      ; NPC доверяет игроку
    (is-hostile ?npc - agent)                  ; NPC враждебен (КРАСНАЯ ЛИНИЯ)
    (has-item ?player - agent ?i - item)       ; У игрока есть предмет
    (requires-item ?s - secret ?i - item)      ; Для раскрытия тайны нужен предмет
    (has-trait ?npc - agent ?t - trait)        ; У NPC есть черта личности
    (secret-revealed ?s - secret)              ; ТАЙНА РАСКРЫТА (GOAL)
  )

  ; --- ДЕЙСТВИЯ ---

  ; Выдать секрет (сработает только если есть ПРЕДМЕТ и НЕТ ВРАЖДЕБНОСТИ)
  (:action reveal-secret
    :parameters (?npc - agent ?player - agent ?s - secret ?i - item)
    :precondition (and 
        (not (is-hostile ?npc))
        (has-item ?player ?i)
        (requires-item ?s ?i)
    )
    :effect (and 
        (secret-revealed ?s)
        (trusts ?npc ?player)
    )
  )

  ; Обидеться (Пересечение красной линии)
  (:action cross-red-line
    :parameters (?npc - agent ?player - agent)
    :precondition (not (is-hostile ?npc))
    :effect (and 
        (is-hostile ?npc)
        (not (trusts ?npc ?player))
    )
  )

  ; Подкупить (Если NPC жадный)
  (:action bribe
    :parameters (?npc - agent ?player - agent ?i - item ?t - trait)
    :precondition (and 
        (has-item ?player ?i)
        (has-trait ?npc ?t)
        ; допустим trait_greedy
    )
    :effect (trusts ?npc ?player)
  )
)
