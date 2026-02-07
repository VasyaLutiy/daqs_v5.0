```mermaid
graph TD
    classDef pathClass stroke:#00ff00,stroke-width:2px
    classDef containsClass stroke:#0000ff,stroke-dasharray: 5 5
    classDef linkClass stroke:#ff0000,stroke-width:3px
    classDef hasClass stroke:#ffa500,stroke-dasharray: 10 5
    classDef locationClass stroke:#00ff00,stroke-width:2px
    classDef itemClass stroke:#0000ff,stroke-dasharray: 5 5
    classDef npcClass stroke:#ff0000,stroke-width:3px
    classDef objectClass stroke:#ffa500,stroke-dasharray: 10 5
    subgraph ancient_temple["Ancient Temple"]
        ancient_temple_entrance("Ancient Temple Entrance"):::locationClass
        temple_guardian[["Temple Guardian"]]:::npcClass
        ancient_temple_entrance -. contains .-> temple_guardian
        temple_door{"Temple Door"}:::objectClass
        ancient_temple_entrance -. contains .-> temple_door
        temple_altar("Temple Altar"):::locationClass
        altar{"Altar"}:::objectClass
        temple_altar -. contains .-> altar
        temple_hall("Temple Hall"):::locationClass
        ancient_artifact("Ancient Artifact"):::itemClass
        temple_hall -. contains .-> ancient_artifact
        npc_paladin_guard[["Sir Aric"]]:::npcClass
        temple_hall -. contains .-> npc_paladin_guard
        loc_secret_lab("Arcane Weaving Sanctum"):::locationClass
        item_prototype("Aetheric Prototype"):::itemClass
        loc_secret_lab -. contains .-> item_prototype
        npc_megan[["Megan the Mystic"]]:::npcClass
        loc_secret_lab -. contains .-> npc_megan
        anc_hidden_grove("Ancient Hidden Grove"):::locationClass
        obj_fort_portal{"Ancient Stone Portal"}:::objectClass
        anc_hidden_grove -. contains .-> obj_fort_portal
    end
    subgraph enchanted_forest["Enchanted Forest"]
        hidden_grove("Hidden Grove"):::locationClass
        summoning_rune("Summoning Rune"):::itemClass
        hidden_grove -. contains .-> summoning_rune
        dark_thicket("Dark Thicket"):::locationClass
        shadow_guards[["Shadow Guards"]]:::npcClass
        dark_thicket -. contains .-> shadow_guards
        dark_crystal{"Dark Crystal"}:::objectClass
        dark_thicket -. contains .-> dark_crystal
        forest_clearing("Forest Clearing"):::locationClass
        forest_herbs("Forest Herb"):::itemClass
        forest_clearing -. contains .-> forest_herbs
        forest_entrance("Forest Entrance"):::locationClass
        ancient_oak{"Ancient Oak"}:::objectClass
        forest_entrance -. contains .-> ancient_oak
        tavern("Broken Cask Tavern"):::locationClass
        npc_dolores[["Dolores"]]:::npcClass
        tavern -. contains .-> npc_dolores
    end
    subgraph region_epic_quest["The Forgotten Lands"]
        loc_fort("The Forest Fort"):::locationClass
        cpt_heat_potion("Fire Resistance Elixir"):::itemClass
        loc_fort -. contains .-> cpt_heat_potion
        npc_blacksmith[["Old Blacksmith"]]:::npcClass
        loc_fort -. contains .-> npc_blacksmith
        loc_peak("Volcano Peak"):::locationClass
        cpt_feather("Phoenix Feather"):::itemClass
        loc_peak -. contains .-> cpt_feather
        loc_bridge("The Dragon Bridge"):::locationClass
        loc_citadel("The Citadel"):::locationClass
    end
    subgraph mystical_bridge["Mystical Bridge"]
        bridge_crossing("Bridge Crossing"):::locationClass
        templedoor_key("TempleDoor Key"):::itemClass
        bridge_crossing -. contains .-> templedoor_key
    end
    subgraph paladin_realm["Paladin Realm"]
        paladin_hall("Paladin Hall"):::locationClass
        mighty_blade("Mighty Blade"):::itemClass
        paladin_hall -. contains .-> mighty_blade
        spirit_of_blade[["Spirit of Blade"]]:::npcClass
        paladin_hall -. contains .-> spirit_of_blade
        golem_of_hall[["Golem of Hall"]]:::npcClass
        paladin_hall -. contains .-> golem_of_hall
        connecting_hall("Connecting Hall"):::locationClass
        item_shadow_coin("Black Iron Coin"):::itemClass
        connecting_hall -. contains .-> item_shadow_coin
        paladin_chamber("Paladin Chamber"):::locationClass
        portal_crystal("Portal Crystal"):::itemClass
        paladin_chamber -. contains .-> portal_crystal
        spirit_of_paladin_aeorha[["Spirit of Paladin Aeorha"]]:::npcClass
        paladin_chamber -. contains .-> spirit_of_paladin_aeorha
        golem_of_chamber[["Golem of Chamber"]]:::npcClass
        paladin_chamber -. contains .-> golem_of_chamber
        connecting_bridge("Connecting Bridge"):::locationClass
        paladin_entrance("Paladin Entrance"):::locationClass
        portal_rune("Portal Rune"):::itemClass
        paladin_entrance -. contains .-> portal_rune
        spirit_of_rune[["Spirit of Rune"]]:::npcClass
        paladin_entrance -. contains .-> spirit_of_rune
    end
    anc_hidden_grove -->|portal| loc_fort
    ancient_temple_entrance -->|path| dark_thicket
    ancient_temple_entrance -->|door| temple_hall
    temple_altar -->|path| temple_hall
    temple_hall -->|door| ancient_temple_entrance
    temple_hall -->|path| temple_altar
    loc_secret_lab <-->|door| temple_hall
    temple_hall <-->|door| loc_secret_lab
    anc_hidden_grove <-->|path| temple_altar
    temple_altar <-->|path| anc_hidden_grove
    hidden_grove -->|path| forest_clearing
    dark_thicket -->|path| forest_clearing
    dark_thicket -->|path| ancient_temple_entrance
    dark_thicket -->|path| bridge_crossing
    forest_clearing -->|path| hidden_grove
    forest_clearing -->|path| dark_thicket
    forest_entrance <-->|path| forest_clearing
    forest_clearing <-->|path| forest_entrance
    tavern <-->|path| forest_clearing
    forest_clearing <-->|path| tavern
    loc_fort <-->|path| loc_peak
    loc_peak <-->|path| loc_fort
    loc_peak <-->|path| loc_bridge
    loc_bridge <-->|path| loc_peak
    loc_bridge <-->|door| loc_citadel
    loc_citadel <-->|door| loc_bridge
    bridge_crossing -->|path| dark_thicket
    bridge_crossing -->|path| paladin_entrance
    paladin_hall -->|path| connecting_bridge
    paladin_hall -->|path| connecting_hall
    connecting_hall -->|path| paladin_hall
    connecting_hall -->|path| paladin_chamber
    paladin_chamber -->|path| connecting_hall
    connecting_bridge -->|path| paladin_entrance
    connecting_bridge -->|path| paladin_hall
    paladin_entrance -->|leads_to| bridge_crossing
    paladin_entrance -->|path| connecting_bridge
    templedoor_key -->|linked| temple_door
    npc_paladin_guard -. has .-> item_sun_blade
    npc_paladin_guard -. has .-> item_silver_plate
    npc_megan -. has .-> item_crystal_staff
    npc_megan -. has .-> item_star_robe
    shadow_guards -. has .-> templedoor_key
    linkStyle 27 stroke:#00ff00,stroke-width:2px
    linkStyle 28 stroke:#00ff00,stroke-width:2px
    linkStyle 29 stroke:#00ff00,stroke-width:2px
    linkStyle 30 stroke:#00ff00,stroke-width:2px
    linkStyle 31 stroke:#00ff00,stroke-width:2px
    linkStyle 32 stroke:#00ff00,stroke-width:2px
    linkStyle 33 stroke:#00ff00,stroke-width:2px
    linkStyle 34 stroke:#00ff00,stroke-width:2px
    linkStyle 35 stroke:#00ff00,stroke-width:2px
    linkStyle 36 stroke:#00ff00,stroke-width:2px
    linkStyle 37 stroke:#00ff00,stroke-width:2px
    linkStyle 38 stroke:#00ff00,stroke-width:2px
    linkStyle 39 stroke:#00ff00,stroke-width:2px
    linkStyle 40 stroke:#00ff00,stroke-width:2px
    linkStyle 41 stroke:#00ff00,stroke-width:2px
    linkStyle 42 stroke:#00ff00,stroke-width:2px
    linkStyle 43 stroke:#00ff00,stroke-width:2px
    linkStyle 44 stroke:#00ff00,stroke-width:2px
    linkStyle 45 stroke:#00ff00,stroke-width:2px
    linkStyle 46 stroke:#00ff00,stroke-width:2px
    linkStyle 47 stroke:#00ff00,stroke-width:2px
    linkStyle 48 stroke:#00ff00,stroke-width:2px
    linkStyle 49 stroke:#00ff00,stroke-width:2px
    linkStyle 50 stroke:#00ff00,stroke-width:2px
    linkStyle 51 stroke:#00ff00,stroke-width:2px
    linkStyle 52 stroke:#00ff00,stroke-width:2px
    linkStyle 53 stroke:#00ff00,stroke-width:2px
    linkStyle 54 stroke:#00ff00,stroke-width:2px
    linkStyle 55 stroke:#00ff00,stroke-width:2px
    linkStyle 56 stroke:#00ff00,stroke-width:2px
    linkStyle 57 stroke:#00ff00,stroke-width:2px
    linkStyle 58 stroke:#00ff00,stroke-width:2px
    linkStyle 59 stroke:#00ff00,stroke-width:2px
    linkStyle 60 stroke:#00ff00,stroke-width:2px
    linkStyle 61 stroke:#00ff00,stroke-width:2px
    linkStyle 62 stroke:#00ff00,stroke-width:2px
    linkStyle 63 stroke:#00ff00,stroke-width:2px
    linkStyle 0 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 1 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 2 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 3 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 4 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 5 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 6 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 7 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 8 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 9 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 10 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 11 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 12 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 13 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 14 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 15 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 16 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 17 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 18 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 19 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 20 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 21 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 22 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 23 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 24 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 25 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 26 stroke:#0000ff,stroke-dasharray: 5 5
    linkStyle 64 stroke:#ff0000,stroke-width:3px
    linkStyle 65 stroke:#ffa500,stroke-dasharray: 10 5
    linkStyle 66 stroke:#ffa500,stroke-dasharray: 10 5
    linkStyle 67 stroke:#ffa500,stroke-dasharray: 10 5
    linkStyle 68 stroke:#ffa500,stroke-dasharray: 10 5
    linkStyle 69 stroke:#ffa500,stroke-dasharray: 10 5
    ```