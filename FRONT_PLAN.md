  # План: React-frontend для DAQS с multi-user guest sessions и game-like UI/UX

  ## Summary

  Новый фронтенд проектируется как отдельное Next.js-приложение на TypeScript, desktop-first responsive, с фокусом на core loop:
  exploration, dialogue, quest acceptance, inventory/status и session-safe resume. Текущий Streamlit-dashboard остаётся внутренним
  debug-инструментом и не развивается как продуктовый UI.

  Для v1 принимаются такие продуктовые решения:

  - Session model: изолированные guest sessions без логина.
  - Stack: Next.js App Router.
  - Scope: core gameplay loop, без full parity с debug-панелями Streamlit.
  - Backend scope: фронтенд и необходимые API-доработки делаются вместе.
  - Visual direction: hybrid fantasy-tech.

  ## Анализ текущего Streamlit dashboard

  - Текущий UI в social_webui_ent.py — это один монолитный файл примерно на 580 строк, без модульной композиции, без маршрутизации и без
    разделения на domain/UI/data layers.
  - Клиент сам собирает состояние игрока через st.session_state и локальный player_state.json. Это подходит для single-user debug, но не
    подходит для реального multi-user режима.
  - Основной UX жёстко зашит в два режима: WORLD и SOCIAL. Это ускоряет отладку, но не даёт гибко строить игровые состояния, модальные
    переходы и восстановление сессии.
  - API слой не типизирован. requests вызывается напрямую, ошибки отрабатываются локально в UI, схемы ответов не валидируются на
    клиенте.
  - В основной интерфейс протаскивается отладочная информация: raw world cache, graphviz-графы, backend valid moves, internal monologue,
    служебные кнопки reset/cache clear.
  - Визуально интерфейс больше похож на operational console/debug deck, чем на игру: нет устойчивой визуальной иерархии, нет целевого
    art direction, нет продуктовой onboarding-структуры, нет mobile adaptation strategy.
  - Что стоит сохранить: чёткий split на world/social loop, быстрый доступ к inventory и quest state, визуальные сцены, sidebar quick
    actions как идея контекстных геймплейных shortcuts.

  ## Целевой продукт и архитектура

  - Создать отдельный frontend workspace frontend/ на Next.js + TypeScript.
  - Использовать App Router.
  - Основной runtime — client-driven game shell; server components оставить для shell bootstrapping, статики и route-level layout.
  - Для API и кэша использовать TanStack Query.
  - Для локального UI-state использовать Zustand.
  - Для runtime schema validation использовать Zod.
  - Для motion и reveal-анимаций использовать Framer Motion.
  - Для стилей использовать Tailwind CSS + собственные design tokens через CSS variables.
  - Streamlit не удалять; оставить как internal debug app, но больше не считать его основным UX.

  ### Routing

  - / — landing/start screen с entry CTA Start Journey.
  - /play — создание новой guest session или восстановление последней локальной session.
  - /play/[gameSessionId] — основной игровой shell.
  - /debug/[gameSessionId] — debug-only route, доступная только в dev/staging или за feature flag.

  ### Client state boundaries

  - Backend становится authoritative source of truth для player/world/social state.
  - Frontend хранит только UI state, активные панели, локальные предпочтения, последний gameSessionId и временные optimistic flags.
  - player_state.json и любая file-based persistence убираются из пользовательского сценария.
  - Никакой клиентской сборки world/social state для gameplay-логики в production UI не остаётся.

  ## Новый backend contract

  Новый React-клиент не должен работать через legacy endpoints, которые требуют собирать player_state на клиенте. Для него добавляется
  session-scoped API, а текущие endpoints остаются legacy/debug-compatible.

  ### Session APIs

  - POST /game/sessions
      - Назначение: создать новую guest session.
      - Response: game_session_id, player_id, created_at, expires_at, player_snapshot, world_snapshot.
  - GET /game/sessions/{game_session_id}
      - Назначение: восстановить текущую сессию после refresh/reopen.
      - Response: player_snapshot, world_snapshot, active_social_session, active_quest, ui_context.
  - TTL guest session по умолчанию: 24 часа неактивности с sliding refresh.
  - Frontend хранит game_session_id в localStorage; если session expired или not found, создаёт новую.

  ### World APIs

  - GET /game/sessions/{game_session_id}/world
      - Возвращает server-side world snapshot для основного shell.
  - POST /game/sessions/{game_session_id}/world/move
      - Request: target_location_id.
      - Response: обновлённые player_snapshot, world_snapshot, narrative_event.
  - POST /game/sessions/{game_session_id}/world/pickup
      - Request: item_id.
      - Response: обновлённые player_snapshot, world_snapshot, narrative_event.
  - POST /game/sessions/{game_session_id}/world/plan
      - Request: goal.
      - Response: plan summary, quest hints, updated snapshot if needed.

  ### Quest APIs

  - POST /game/sessions/{game_session_id}/quests/preview
      - Request: quest_goal, quest_name.
      - Response: mission briefing payload, plan summary, difficulty concept.
  - POST /game/sessions/{game_session_id}/quests/accept
      - Request: quest_goal, quest_name.
      - Response: updated player_snapshot, active_quest, world_snapshot.

  ### Social APIs

  - POST /game/sessions/{game_session_id}/social/init
      - Request: persona_id, can_quest.
      - Response: social_session_id, persona_summary, social_state, history, scene.
  - POST /game/sessions/{game_session_id}/social/message
      - Request: social_session_id, message, action?.
      - Response: social_state, history_delta, reply, scene, ui_context.
  - POST /game/sessions/{game_session_id}/social/exit
      - Закрывает активный social panel context, но не уничтожает game session.

  ### API policy

  - Production responses не содержат raw debug metadata, raw graph payloads и backend valid moves.
  - Debug data доступна только через /debug/* endpoints или debug=true в dev/staging окружении.
  - Включить CORS для React frontend origin.
  - Legacy endpoints сохранить как совместимый слой для Streamlit до завершения миграции.

  ## React UI/UX и визуальный дизайн

  ### Experience model

  Основной UX строится как Game Shell, а не как dashboard:

  - Центр: narrative stage с иллюстрацией сцены, диалогом и primary actions.
  - Левая колонка: world/status rail с location, objective, inventory summary, quest tracker.
  - Правая колонка: context drawer для NPC, social stance, actionable choices, quest details.
  - Нижняя зона: command bar / action composer.

  ### Main screens

  - Start Screen: cinematic hero, краткий лор, CTA создать сессию, resume последней сессии.
  - World Exploration View: location art, exits, items, nearby NPCs, активный objective.
  - Dialogue View: NPC portrait/scene, dialogue feed, selectable actions, quest hooks.
  - Quest Journal Overlay: активный квест, шаги, награды, progression.
  - Inventory & Status Drawer: ключевые предметы, concepts/status, без debug overload.
  - Session Menu: restart session, resume info, help, sound/visual toggles.

  ### Visual system

  - Арт-направление: hybrid fantasy-tech.
  - Базовая палитра: obsidian background, parchment bronze surfaces, cyan system glow, ember accent, muted moss/iron neutrals.
  - Типографика: display font Cinzel или Cormorant SC для headings; UI font Space Grotesk; system/debug font IBM Plex Mono.
  - Фон: layered gradients + subtle noise + map-like glyph overlays; избегать плоского однотонного фона.
  - Motion: мягкий scene reveal, drawer slide, quest card stagger, hover glows на интерактивных world nodes.
  - Основной визуальный принцип: “ancient oracle UI meets tactical command console”.
  - Mobile adaptation: shell схлопывается в stacked layout с bottom sheets и segmented tabs; desktop остаётся primary target.

  ### UX rules

  - В primary flow не показывать JSON, raw plans, raw DOT graphs, internal monologue.
  - Один экран — одна доминирующая задача.
  - Всегда видны: current objective, location, active NPC state или current dialogue context.
  - Secondary info открывается через drawers/overlays, а не через постоянные debug expander-блоки.
  - Для долгих операций показывать cinematic loading states, а не технические спиннеры без контекста.

  ## Frontend implementation plan

  ### Phase 1: Foundations

  - Поднять Next.js приложение, настроить TypeScript, Tailwind, TanStack Query, Zustand, Zod, Framer Motion.
  - Создать API client layer с типизированными request/response schemas.
  - Реализовать SessionProvider, который создаёт, восстанавливает и инвалидирует game_session_id.
  - Реализовать базовый shell layout и route guards для session-aware screens.

  ### Phase 2: World core loop

  - Реализовать start/resume flow.
  - Реализовать world screen с location art, exits, item pickup, NPC interaction cards.
  - Перевести inventory, objective, location and quest summary в persistent side rail.
  - Подключить server-driven world snapshot без client-authored player_state.

  ### Phase 3: Social loop

  - Реализовать dialogue scene view с отдельным social_session_id.
  - Подключить init/message/exit flow.
  - Добавить action chips, fallback free-text input, context-sensitive quest prompts.
  - Историю сообщений рендерить как narrative feed, а не как raw chat/debug stream.

  ### Phase 4: Quest layer and polish

  - Реализовать quest preview/accept flow.
  - Добавить journal overlay и mission cards.
  - Добавить motion polish, transitions, loading/fallback states, mobile collapse behaviour.
  - Добавить debug route для graphs, valid moves и backend internals, чтобы продуктовый UI оставался чистым.

  ## Test plan

  - Unit tests для session store hooks, API schema parsing, route transitions, UI stores.
  - Integration tests для session bootstrap, resume after refresh, world move, pickup, quest accept, social init/message.
  - E2E tests в двух параллельных browser contexts: действия пользователя A не влияют на inventory/history/session пользователя B.
  - E2E tests на refresh/reopen: game_session_id поднимается из localStorage, shell восстанавливает актуальный snapshot.
  - Contract tests между React client и новым FastAPI session-scoped API.
  - Responsive tests для desktop и mobile breakpoints.
  - Visual regression tests для start screen, world view, dialogue view, quest overlay.
  - Acceptance сценарии:
      - новый игрок создаёт сессию и попадает в world view;
      - игрок перемещается, подбирает предмет и видит обновлённый state;
      - игрок начинает диалог с NPC и получает отдельный social_session_id;
      - игрок принимает квест и возвращается в world view с обновлённым objective;
      - второй пользователь проходит тот же flow независимо;
      - expired session корректно сбрасывается в новый start flow.

  ## Assumptions

  - V1 не включает auth/accounts.
  - V1 не включает shared real-time multiplayer world.
  - V1 не требует full parity со Streamlit debug UI.
  - Streamlit остаётся internal tool и не диктует публичный UX.
  - WebSocket/realtime transport в v1 не нужен; достаточно REST.
  - Image generation остаётся progressive enhancement: если визуал не готов вовремя, UI показывает styled fallback scene card без
    блокировки core loop.
