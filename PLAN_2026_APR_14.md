# PLAN_2026_APR_14 — Рефакторинг PDDL-архитектуры DAQS v5.1 Enterprise

**Дата старта:** 2026-04-14  
**Ветка:** `v5.1_enterprise`  
**Цель:** Правильная архитектура PDDL-планировщика, устранение семантического дрейфа,
качественное тестовое покрытие PDDL-логики.

---

## Принципы рефакторинга

1. **PDDL — инструмент планирования, не исполнения.** Диалоговый граф — конечный автомат (FSM), не задача планирования. PDDL остаётся только для квестов и oracle-режима.
2. **Компиляция один раз при старте.** Все YAML → типизированные объекты при `uvicorn` startup. Ошибки конфига видны сразу.
3. **Нет мутации `Dict[str, Any]`.** `SocialState` — immutable dataclass с методом `copy()`.
4. **Один источник правды.** Семантика переходов живёт в `DialogueEngine`, не дублируется в `MoveValidator` + `StateManager` + PDDL-домене.
5. **Тесты прежде рефакторинга.** Каждый рефакторируемый компонент закрывается тестами до правки.

---

## Фазы реализации

---

### ФАЗА 0 — Фиксация текущего состояния и критических багов
**Статус:** `[x] выполнено (2026-04-14)`

Цель: исправить критические баги не меняя архитектуру, чтобы система работала корректно
во время рефакторинга.

#### Задачи

- [x] **0.1** Исправить дублированное поле `player_state` в `SocialInitRequest`  
  Файл: `npc_engine/main_fast_ent.py`  
  Удалена строка-дубликат.

- [x] **0.2** Исправить несоответствие имён домена  
  Файл: `npc_engine/config/logic/social/problem.pddl.j2:3`  
  `(:domain narrative-flow)` → `(:domain narrative-flow-v2)` ✓

- [x] **0.3** Убрать попытку загрузки несуществующего V4 шаблона  
  Файл: `npc_engine/engine/master/pddl_orchestrator.py`  
  `get_domain("social")` теперь напрямую вызывает `social_domain_v2.pddl.j2` без ERROR-fallback.

- [x] **0.4** Вынести `import re` из тела метода на уровень модуля  
  Файл: `npc_engine/engine/master/pddl_orchestrator.py` ✓

- [x] **0.5** Заменить `list.pop(0)` на `deque.popleft()` в BFS-диагностике  
  Файл: `npc_engine/engine/master/planner_libs.py` ✓ (добавлен `from collections import deque`)

- [x] **0.6** Удалить мёртвый код  
  - ~~`npc_engine/engine/world/social_pddl_gen.py`~~ — удалён
  - ~~`npc_engine/engine/master/planner_diagnostics.py`~~ — удалён
  - ~~`npc_engine/config/social_world/social_domain.pddl`~~ — удалён
  - ~~Закомментированный блок `'''...'''` в `gamemaster/visual_generator.py:235-283`~~ — удалён
  - ~~No-op функция `_apply_shadow_goal_logic`~~ — удалена (2 call sites тоже убраны)

- [x] **0.7** Задокументировать намеренную мутацию `objects` в `build_social_init_facts`  
  Файл: `npc_engine/engine/master/pddl_libs.py`  
  Добавлен docstring-комментарий поясняющий контракт: мутация намеренная, caller должен
  передавать тот же список что используется для `:objects`.

- [x] **0.8** Убрать `datetime.utcnow()` (deprecated Python 3.12+)  
  Заменено на `datetime.now(timezone.utc)` везде в `main_fast_ent.py` ✓

#### Тесты для Фазы 0

- [x] **test_0.1** `SocialInitRequest` имеет ровно одно поле `player_state` — `tests/test_phase0_fixes.py`
- [x] **test_0.2** `problem.pddl.j2` содержит `(:domain narrative-flow-v2)` — `tests/test_phase0_fixes.py`
- [x] **test_0.3** `get_domain("social")` возвращает домен V2 без ERROR — `tests/test_phase0_fixes.py`
- [x] **test_0.7** `build_social_init_facts` не мутирует objects когда mood уже известен — `tests/test_phase0_fixes.py`

**Результат:** 5/5 тестов проходят (`pytest tests/test_phase0_fixes.py` в daqs5 venv)

---

### ФАЗА 1 — Типизированный SocialState + тесты
**Статус:** `[x] выполнено (2026-04-14)`

Цель: заменить `Dict[str, Any]` на типизированный `SocialState`. Это фундамент для
остальных фаз.

#### Задачи

- [x] **1.1** Создать `npc_engine/engine/dialogue/state.py`

  ```python
  @dataclass(frozen=True)   # immutable
  class SocialState:
      persona_id: str
      current_context: str
      goal_context: str
      concepts: frozenset[str]
      visited_contexts: frozenset[str]
      exhausted_triggers: frozenset[str]
      shared_items: frozenset[str]
      current_mood: str
      oracle_path: tuple[str, ...] | None  # предвычисленный путь
      can_quest: bool
  
      def with_context(self, ctx_id: str) -> "SocialState":
          return dataclasses.replace(
              self,
              current_context=ctx_id,
              visited_contexts=self.visited_contexts | {ctx_id}
          )
  
      def with_concept(self, concept_id: str) -> "SocialState":
          return dataclasses.replace(self, concepts=self.concepts | {concept_id})
  
      def with_trigger_exhausted(self, trigger_id: str) -> "SocialState":
          return dataclasses.replace(self, exhausted_triggers=self.exhausted_triggers | {trigger_id})
  
      def to_pddl_facts(self) -> list[str]:
          """Экспорт для PDDL-планировщика (oracle/quest modes)."""
          facts = [f"(active-context player {self.current_context})"]
          facts += [f"(has-concept player {c})" for c in sorted(self.concepts)]
          facts += [f"(visited {ctx})" for ctx in sorted(self.visited_contexts)]
          facts += [f"(exhausted {t})" for t in sorted(self.exhausted_triggers)]
          if self.current_mood:
              facts += [f"(current-mood player {self.current_mood})"]
          return facts
  
      @classmethod
      def from_dict(cls, d: dict) -> "SocialState":
          """Обратная совместимость: создать из старого dict-формата."""
          ...
  
      def to_dict(self) -> dict:
          """Сериализация для API-ответа."""
          ...
  ```

- [x] **1.2** Создать `npc_engine/engine/dialogue/__init__.py`

- [x] **1.3** Адаптировать `social_init` и `social_message` эндпоинты для работы с
  `SocialState`, сохраняя обратную совместимость API через `to_dict()` / `from_dict()`

#### Тесты для Фазы 1

- [x] **test_1.1** `SocialState` — immutable: `with_context()` не мутирует оригинал
- [x] **test_1.2** `with_concept()` корректно добавляет концепт (+ idempotent)
- [x] **test_1.3** `with_trigger_exhausted()` корректно помечает триггер
- [x] **test_1.4** `to_pddl_facts()` — 7 тестов: нет дубликатов, синтаксис, mood, active-context
- [x] **test_1.5** `from_dict()` / `to_dict()` — round-trip без потерь, legacy key support
- [x] **test_1.6** `to_pddl_facts()` → `validate_problem_predicates` → нет ошибок

**Результат:** 22/22 тестов (Ф0+Ф1) проходят; pre-existing failure в `test_pddl_validation.py::test_validation_rejects_unknown_predicates` существовала до нашего рефакторинга.

**Новые файлы:**
- `npc_engine/engine/dialogue/__init__.py`
- `npc_engine/engine/dialogue/state.py` — `SocialState` frozen dataclass
- `tests/test_phase1_social_state.py` — 17 тестов

---

### ФАЗА 2 — Domain Compiler + тесты
**Статус:** `[x] выполнено (2026-04-14)`

Цель: компилировать YAML один раз при старте, обнаруживать ошибки конфига до запуска.

#### Задачи

- [x] **2.1** Создать `npc_engine/engine/compiler.py` с классами:

  ```
  ConfigError(Exception)          — ошибка валидации конфига
  DialogueTransition              — один переход между контекстами с условием
  TransitionCondition             — requires_concept | requires_combo | requires_item
  CompiledContext                 — контекст с предвычисленными переходами
  CompiledDialogueGraph           — полный граф персоны
  CompiledWorldGraph              — физический мир (обёртка WorldGraph)
  DomainCompiler                  — компилирует YAML → объекты
  ```

- [x] **2.2** `DomainCompiler.compile_persona_file(yaml_path)`:
  - Поддерживает atlas-format (persona_group) и standalone
  - Проверяет: все `to:` → существующие ctx ID
  - Проверяет: все `required_concept` / `yields` / combo → существующие concept ID
  - Строит `transitions: dict[str, tuple[DialogueTransition, ...]]` (freeze-on-compile)
  - Бросает `ConfigError` при нарушении ссылочной целостности

- [x] **2.3** `DomainCompiler.compile_all(config_dir)`:
  - Компилирует все persona YAML из `social_world/nodes/personas/`
  - Логирует ошибки отдельных файлов без падения остальных
  - Возвращает `dict[str, CompiledDialogueGraph]`

- [x] **2.4** Интегрировать в FastAPI startup event → `DIALOGUE_GRAPHS` global заполняется при старте

- [x] **2.5** `GET /health` расширен: `personas_loaded`, `persona_ids`

**Попутно исправлен баг конфига:** `orcs.yaml` — `cpt_agreement` использовался как `required_concept` но не был объявлен в concepts. Добавлен в atlas-level concepts.

#### Тесты для Фазы 2

- [x] **test_2.1** `compile_persona_file(cyber.yaml)` — 4 ctx, 3 triggers, transitions, concepts
- [x] **test_2.2** `compile_persona_file(paladin.yaml)` — atlas concepts, start context, locked goal
- [x] **test_2.3** Unknown `required_concept` → `ConfigError` с упоминанием имени концепта
- [x] **test_2.4** Unknown `to:` → `ConfigError`; + trigger с unknown parent_context → `ConfigError`
- [x] **test_2.5** `compile_all()` — все 7 реальных персон загружены, start_context валиден
- [x] **test_2.6** Идемпотентность: два вызова `compile_all()` → одинаковые context/concept/trigger наборы
- [x] **test_2.7** Transitions: нет self-loop, все to_ctx существуют, YAML-edges совпадают с transition map

**Результат:** 32/32 тестов (Ф0+Ф1+Ф2) проходят

**Новые файлы:**
- `npc_engine/engine/compiler.py` — `ConfigError`, `TransitionCondition`, `DialogueTransition`, `CompiledContext`, `CompiledTrigger`, `CompiledDialogueGraph`, `DomainCompiler`
- `tests/test_phase2_compiler.py` — 10 тестов

---

### ФАЗА 3 — DialogueEngine (FSM) + тесты
**Статус:** `[~] в работе`

Цель: заменить `MoveValidator` + `StateManager` единым `DialogueEngine`, который
является единственным источником правды для диалоговых переходов.

#### Задачи

- [ ] **3.1** Создать `npc_engine/engine/dialogue/engine.py`

  ```python
  @dataclass
  class DialogueMove:
      action: str           # PDDL-формат: "shift-context player ctx_a ctx_b"
      move_type: str        # "shift" | "trigger" | "learn" | "unlock" | "combo"
      to_ctx: str | None = None
      concept_gained: str | None = None
      trigger_id: str | None = None
  
  class DialogueEngine:
      def __init__(self, graph: CompiledDialogueGraph): ...
  
      def get_valid_moves(self, state: SocialState) -> list[DialogueMove]:
          """O(k) — обход скомпилированного графа."""
  
      def apply_move(self, move: DialogueMove, state: SocialState) -> SocialState:
          """Чистая функция. (state, move) → new_state."""
  
      def is_goal_reached(self, state: SocialState) -> bool: ...
  
      def get_oracle_next_step(self, state: SocialState) -> DialogueMove | None:
          """Следующий шаг по предвычисленному oracle_path."""
  ```

- [ ] **3.2** `get_valid_moves()` — логика:
  - Для каждого `transition` из `transitions[state.current_context]`:
    - Если `to_ctx` не заблокирован → `shift-context`
    - Если заблокирован и условие выполнено → `apply-concept` / `apply-combo-concept`
  - Триггеры текущего контекста не в `exhausted_triggers` → `activate-trigger`
  - `provides_concept` текущего контекста не в `concepts` → `learn-concept`
  - V2 behavior_rules по текущему mood → `do_{rule_id}`

- [ ] **3.3** `apply_move()` — чистая функция без мутации:
  - `shift-context` → `state.with_context(to_ctx)` + mood induction
  - `activate-trigger` → `state.with_concept(c).with_trigger_exhausted(t)`
  - `learn-concept` → `state.with_concept(c)`
  - `apply-concept` / `apply-combo-concept` → unlock + move (атомарно)

- [ ] **3.4** Подключить к `social_message` эндпоинту. Убрать `MoveValidator` и
  `StateManager` из пути исполнения.

- [ ] **3.5** Проверить что `get_valid_moves(state)` даёт те же результаты что
  PDDL-планировщик на той же state (golden-test с сохранёнными примерами).

#### Тесты для Фазы 3

- [ ] **test_3.1** `get_valid_moves()` из начального контекста `cyber.yaml`:
  - Содержит `shift-context` к unlocked контекстам
  - Не содержит `shift-context` к locked без нужного концепта
  - Содержит `activate-trigger` для триггеров текущего ctx

- [ ] **test_3.2** `get_valid_moves()` после получения `cpt_trust`:
  - Теперь содержит `apply-concept ... ctx_deep cpt_trust`

- [ ] **test_3.3** `apply_move(shift-context)` — чистота:
  - Оригинальный state не изменён
  - Новый state имеет правильный `current_context`
  - `visited_contexts` обновлён

- [ ] **test_3.4** `apply_move(activate-trigger)`:
  - Концепт добавлен в `concepts`
  - Триггер добавлен в `exhausted_triggers`
  - Повторный вызов `get_valid_moves` не содержит этот триггер

- [ ] **test_3.5** `apply_move(apply-concept)` — атомарный unlock+move:
  - Контекст разблокирован И агент перемещён за один вызов
  - (Устраняет семантический дрейф PDDL ↔ StateManager)

- [ ] **test_3.6** Combo unlock: `apply-combo-concept` — оба концепта нужны,
  при нехватке одного → `get_valid_moves` не содержит combo-move

- [ ] **test_3.7** V2 behavior_rules: при mood `neutral` с нужным item-тегом →
  `do_{rule_id}` в `get_valid_moves()`

- [ ] **test_3.8** Mood induction: `apply_move(shift-context к ctx с induces_mood)` →
  `new_state.current_mood == ctx.induces_mood`

- [ ] **test_3.9** `is_goal_reached()` — True только когда `current_context == goal_context`

- [ ] **test_3.10** Полный диалог-сценарий `cyber.yaml`: от `ctx_intro` до `ctx_core`
  через все необходимые шаги (integration test)

- [ ] **test_3.11** Полный диалог-сценарий `paladin.yaml`: mood transitions + behavior rules

- [ ] **test_3.12** Сравнение FSM vs PDDL (golden test):
  Для `cyber.yaml` и `paladin.yaml` — `get_valid_moves()` FSM должен давать
  тот же набор действий что PDDL-планировщик (`MasterPlanner.solve()` с той же state).

---

### ФАЗА 4 — QuestPlanner: async PDDL + кеш + тесты
**Статус:** `[ ] не начато`

Цель: PDDL-планировщик работает асинхронно, не блокирует event loop,
результаты кешируются.

#### Задачи

- [ ] **4.1** Создать `npc_engine/engine/quest/planner.py`:

  ```python
  @dataclass(frozen=True)
  class PlanCacheKey:
      player_id: str
      goal: str
      oracle_mode: bool
      # world_hash: str  # для инвалидации при смене конфига

  @dataclass
  class QuestPlan:
      steps: list[str]
      quest_steps: list[dict]
      error: str | None
      goal: str
      cached: bool = False

  class QuestPlanner:
      def __init__(self, world_graph: WorldGraph, pddl_cache: PlanCache): ...

      async def plan_quest(self, player: PlayerState, goal: str,
                           oracle_mode: bool = False) -> QuestPlan: ...
      # run_in_executor → не блокирует event loop

      async def assess_difficulty(self, player: PlayerState,
                                  world: WorldGraph) -> str: ...
      # возвращает "cpt_quest_easy" | "cpt_quest_hard" | "cpt_quest_none"

      async def compute_oracle_path(self, state: SocialState,
                                    graph: CompiledDialogueGraph) -> tuple[str, ...]: ...
      # вызывается один раз при /social/init
  ```

- [ ] **4.2** `PlanCache` — простой in-memory LRU-кеш:
  - Ключ: `PlanCacheKey`
  - TTL: 5 мин для quest plans, 10 мин для oracle paths
  - Максимум: 1000 записей

- [ ] **4.3** Подключить `QuestPlanner` к `/quest/accept` и `/social/init`
  (oracle path). Удалить синхронные вызовы `PDDLOrchestrator`/`MasterPlanner`
  из endpoint-тел.

- [ ] **4.4** Инициализировать `QuestPlanner` как singleton в FastAPI startup,
  вместе с `DomainCompiler`.

#### Тесты для Фазы 4

- [ ] **test_4.1** `plan_quest()` с exploration goal: возвращает `QuestPlan` с шагами,
  все шаги валидного PDDL-формата
- [ ] **test_4.2** `plan_quest()` с невозможной целью: `QuestPlan(steps=[], error=...)`
- [ ] **test_4.3** Кеш: второй вызов с теми же параметрами → `cached=True`, не запускает
  планировщик повторно
- [ ] **test_4.4** `assess_difficulty()`: easy quest → `cpt_quest_easy`,
  длинный quest → `cpt_quest_hard`, пустой goal → `cpt_quest_none`
- [ ] **test_4.5** `compute_oracle_path()` для `cyber.yaml`: путь
  `[ctx_intro, ctx_deep, ctx_core]` с нужными концептами
- [ ] **test_4.6** Async: `plan_quest()` не блокирует event loop —
  два параллельных вызова выполняются конкурентно
- [ ] **test_4.7** `plan_quest()` oracle_mode=True vs False: oracle даёт более
  короткий или равный план (больше доступных локаций)

---

### ФАЗА 5 — PDDL domain/problem консистентность + тесты
**Статус:** `[ ] не начато`

Цель: один актуальный домен, устранить V1/V2/V4 confusion, полное тестовое
покрытие генерации PDDL.

#### Задачи

- [ ] **5.1** Переименовать единственный используемый домен:
  - `social_domain_v2.pddl.j2` → `social_domain.pddl.j2`
  - `problem.pddl.j2` исправить: `(:domain narrative-flow-v2)` → `(:domain narrative-flow)`
    и переименовать домен в шаблоне тоже → `narrative-flow`

- [ ] **5.2** Удалить:
  - `npc_engine/config/logic/social/domain.pddl` (мёртвая копия)
  - `npc_engine/config/social_world/social_domain.pddl` (мёртвая копия)
  - Ссылки на V4 в коде

- [ ] **5.3** Создать `npc_engine/engine/master/pddl_validator.py`:
  - `validate_domain_problem_pair(domain: str, problem: str) → list[str]`
  - Проверяет: имена доменов совпадают
  - Проверяет: все предикаты в `:init` и `:goal` объявлены в `:predicates`
  - Проверяет: все типы в `:objects` объявлены в `:types`
  - Проверяет: нет дублирующихся фактов в `:init`

- [ ] **5.4** Вызывать `validate_domain_problem_pair` перед каждым `engine.solve()` в
  `MasterPlanner.solve()` — бросать исключение вместо тихого сбоя.

- [ ] **5.5** Добавить golden-test fixtures: сохранить эталонные domain.pddl +
  problem.pddl для каждой персоны в `tests/fixtures/pddl/`

#### Тесты для Фазы 5

- [ ] **test_5.1** Генерация domain для `cyber.yaml`:
  - Содержит все объявленные действия (`shift-context`, `learn-concept`, etc.)
  - Нет `narrative-flow-v2` / `narrative-flow` несоответствия
  - Парсится `PDDLReader` без ошибок

- [ ] **test_5.2** Генерация problem для `cyber.yaml` с начальным state:
  - `(:domain ...)` совпадает с именем сгенерированного домена
  - `(:init ...)` содержит `(active-context player ctx_intro)`
  - `(:goal ...)` содержит `(visited ctx_core)`
  - Нет дублирующихся фактов

- [ ] **test_5.3** Генерация problem для `paladin.yaml`:
  - Mood факты присутствуют: `(current-mood player resolute)`
  - Equipment facts: `(wearing player item_silver_plate)`
  - `(has-tag item_silver_plate armor)` присутствует
  - `(is-tag armor armor)` рефлексивность присутствует

- [ ] **test_5.4** `validate_domain_problem_pair` — happy path: нет ошибок
- [ ] **test_5.5** `validate_domain_problem_pair` — mismatch имён доменов → ошибка
- [ ] **test_5.6** `validate_domain_problem_pair` — неизвестный предикат в `:init` → ошибка
- [ ] **test_5.7** `validate_domain_problem_pair` — неизвестный тип в `:objects` → ошибка
- [ ] **test_5.8** Дублирующийся факт в `:init` → предупреждение или ошибка
- [ ] **test_5.9** Полный round-trip для exploration domain:
  `PlayerState + goal → domain + problem → MasterPlanner.solve() → plan`
  с конкретной картой мира
- [ ] **test_5.10** Полный round-trip для social domain:
  `persona_id + SocialState → domain + problem → MasterPlanner.solve() → plan`
  Проверить что план содержит ожидаемые шаги для `cyber.yaml`
- [ ] **test_5.11** Golden test: сгенерированный domain/problem для `paladin.yaml`
  совпадает с эталонным fixtures (regression test на изменения генерации)
- [ ] **test_5.12** Solve с `forall` precondition (`do_act_cold_stare`):
  Fast-Downward справляется с `:adl` / `forall` — нет падения планировщика

---

### ФАЗА 6 — Рефакторинг API + Session Management + тесты
**Статус:** `[ ] не начато`

Цель: устранить race conditions, изоляцию сессий, async-правильность.

#### Задачи

- [ ] **6.1** Заменить `SOCIAL_SESSIONS: Dict` на потокобезопасное хранилище:
  ```python
  from asyncio import Lock
  class SessionStore:
      def __init__(self):
          self._store: dict[str, SocialState] = {}
          self._lock = Lock()
      async def get(self, key: str) -> SocialState | None: ...
      async def set(self, key: str, state: SocialState) -> None: ...
      async def delete(self, key: str) -> None: ...
  ```

- [ ] **6.2** Добавить `user_id` к ключу сессии — изоляция пользователей:
  `session_key = f"{user_id}:{persona_id}:{session_id or 'default'}"`

- [ ] **6.3** TTL для сессий: неактивные сессии удаляются через 30 минут

- [ ] **6.4** Эндпоинты: все `async def` с тяжёлыми синхронными операциями →
  обернуть в `run_in_executor`

- [ ] **6.5** Кешировать загрузку мира: `WorldGraph` — singleton, не
  пересоздаётся на каждый запрос

- [ ] **6.6** Убрать хардкод `MANUAL_ACTION_GUARDS` из `main_fast_ent.py` в
  конфигурацию персоны

#### Тесты для Фазы 6

- [ ] **test_6.1** `SessionStore` — concurrent writes: 10 параллельных
  `asyncio.gather` с разными `set()` не corrupts данные
- [ ] **test_6.2** Изоляция сессий: два запроса с разным `user_id` + одинаковым
  `persona_id` → независимые состояния
- [ ] **test_6.3** TTL: сессия не существует после истечения TTL
- [ ] **test_6.4** FastAPI TestClient: `POST /social/init` → `POST /social/message`
  → корректный диалоговый flow end-to-end
- [ ] **test_6.5** `POST /social/message` с несуществующей сессией → правильный
  HTTP статус код (400, не 500)
- [ ] **test_6.6** `POST /quest/accept` → async, не блокирует event loop

---

### ФАЗА 7 — Финальная интеграция и regression suite
**Статус:** `[ ] не начато`

#### Задачи

- [ ] **7.1** Запустить полный сценарий `cyber.yaml` через API end-to-end
- [ ] **7.2** Запустить полный сценарий `paladin.yaml` через API end-to-end
- [ ] **7.3** Сравнить поведение до и после рефакторинга на `dialogue_test_Dolores.json`
- [ ] **7.4** Обновить `requirements.txt`:
  - Убрать `pathlib>=1.0.0`, `typing>=3.7.0` (stdlib)
  - Добавить `pytest-asyncio` для async тестов
- [ ] **7.5** Настроить `pytest` конфиг (`pyproject.toml` или `pytest.ini`)
- [ ] **7.6** CI check: все тесты проходят, нет `print()` в production-коде

#### Тесты для Фазы 7

- [ ] **test_7.1** Regression: `test_auto_simulation.py` проходит без изменений
- [ ] **test_7.2** Regression: `test_npc_stats.py` проходит без изменений
- [ ] **test_7.3** Performance: `/social/message` отвечает за < 50ms без LLM
  (только FSM + state update, без PDDL)
- [ ] **test_7.4** Performance: `/quest/accept` с PDDL: первый вызов < 3s,
  повторный (кеш) < 10ms

---

## Карта файлов: что создать / изменить / удалить

### Создать
```
npc_engine/engine/dialogue/__init__.py
npc_engine/engine/dialogue/state.py          # SocialState (immutable dataclass)
npc_engine/engine/dialogue/engine.py         # DialogueEngine (FSM)
npc_engine/engine/compiler.py               # DomainCompiler
npc_engine/engine/quest/planner.py          # QuestPlanner (async PDDL)
npc_engine/engine/quest/__init__.py
npc_engine/engine/master/pddl_validator.py  # validate_domain_problem_pair
tests/fixtures/pddl/cyber_domain.pddl       # golden fixtures
tests/fixtures/pddl/cyber_problem.pddl
tests/fixtures/pddl/paladin_domain.pddl
tests/fixtures/pddl/paladin_problem.pddl
tests/test_social_state.py                  # Фаза 1
tests/test_compiler.py                      # Фаза 2
tests/test_dialogue_engine.py               # Фаза 3
tests/test_quest_planner.py                 # Фаза 4
tests/test_pddl_generation.py               # Фаза 5 (расширяет test_pddl_validation.py)
tests/test_session_store.py                 # Фаза 6
tests/test_api_integration.py               # Фаза 6-7
```

### Изменить
```
npc_engine/engine/master/pddl_orchestrator.py    # убрать V4, исправить fallback
npc_engine/engine/master/planner.py             # добавить pddl_validator
npc_engine/engine/master/planner_libs.py        # deque BFS, убрать дубликат diagnose
npc_engine/engine/master/pddl_libs.py           # убрать мутацию objects
npc_engine/config/logic/social/problem.pddl.j2  # исправить domain name
npc_engine/main_fast_ent.py                      # SessionStore, SocialState, async
```

### Удалить
```
npc_engine/engine/world/social_pddl_gen.py       # мёртвый код + print()
npc_engine/engine/master/planner_diagnostics.py  # дубликат
npc_engine/config/social_world/social_domain.pddl # мёртвая копия
npc_engine/config/logic/social/domain.pddl        # мёртвая копия (заменена v2)
gamemaster/visual_generator.py → убрать блок '''...''' строки 235-283
npc_engine/main_fast_ent.py → убрать MANUAL_ACTION_GUARDS, _apply_shadow_goal_logic
```

---

## Приоритет тестов по критичности

```
P0 (блокирующие — писать первыми):
  test_5.9  полный round-trip exploration PDDL
  test_5.10 полный round-trip social PDDL
  test_3.12 FSM vs PDDL golden comparison
  test_0.2  domain name consistency

P1 (core correctness):
  test_3.1 – 3.9   DialogueEngine FSM
  test_5.1 – 5.8   PDDL generation + validation
  test_1.4          to_pddl_facts()
  test_4.5          oracle path computation

P2 (reliability):
  test_6.1  concurrent session safety
  test_4.6  async non-blocking
  test_2.3  config error detection at compile time

P3 (regression):
  test_5.11  golden domain/problem fixtures
  test_7.1 – 7.4  full regression suite
```

---

## Заметки в процессе работы

> Этот раздел обновляется по мере выполнения задач

### Фаза 0
- [ ] Начато

### Фаза 1
- [ ] Начато

### Фаза 2
- [ ] Начато

### Фаза 3
- [ ] Начато

### Фаза 4
- [ ] Начато

### Фаза 5
- [ ] Начато

### Фаза 6
- [ ] Начато

### Фаза 7
- [ ] Начато

---

## Известные риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| unified_planning молча принимает domain name mismatch | Высокая | Тест 0.2 выяснит это явно |
| Fast-Downward не поддерживает `forall` в preconditions | Средняя | Тест 5.12 верифицирует |
| FSM vs PDDL семантика расходится на edge cases | Средняя | Тест 3.12 golden comparison |
| `apply-concept` unlock-only в PDDL vs move-in-StateManager | Подтверждён | Тест 3.5 + исправление в Фазе 3 |
| Кеш PDDL планов устаревает при смене конфига | Средняя | world_hash в PlanCacheKey (Фаза 4) |
| Persona без behavior_rules: tags в `:objects` vs `:constants` | Низкая | Тест 5.3 покрывает |
