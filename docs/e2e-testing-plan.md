# Plan testów e2e (UI + LLM)

Cel: wyłapywać regresje w całej aplikacji — od pliku journala i modelu LLM aż po
to, co widać w TUI. Testy działają na Textualowym `App.run_test()` + `Pilot`,
bez prawdziwego terminala.

Zasada podziału:

- **Żywy LLM (OpenRouter, darmowy model)** — sprawdza, czy *model* zachowuje się
  dobrze (np. „wysuń podwozie” → narzędzie `perform_game_action` z
  `LandingGearToggle`). Osobna warstwa, na start nieblokująca.
- **Model skryptowany (`FunctionModel`)** — sprawdza, co *nasza aplikacja* robi
  z odpowiedzią modelu (COMMS, stany, błędy). Deterministyczny, blokuje merge.

```
Faza 0 ✅ ──► Faza 1 (scenariusze UI, blokujące) ──┬──► Faza 2 (żywy LLM, eksperyment, nieblokujący)
                                                   └──► Faza 3 (snapshoty)
                                                                └──► Faza 4 (domknięcie)
```

---

## Faza 0 — odblokowanie kodu ✅

| # | Zmiana | Stan |
|---|---|---|
| 0.1 | `SettingsService(config_path, example_config_path)` zamiast `Path("config.yaml")` na sztywno | ✅ |
| 0.2 | `AppConfig()` czytany w `main()` (`container.config.from_pydantic`), import kontenera działa bez `.env` | ✅ |
| 0.3 | `MODULES_USING_PROVIDE` w `main_container.py`, wiring z `main()` i z testów; `tests/containers/test_wired_modules.py` pilnuje kompletności | ✅ |
| 0.4 | `SystemCheckScreen.SECONDS_BEFORE_DASHBOARD` (test ustawia `0`) | ✅ |
| 0.5 | Zegar w `AppHeader` — **bez zmian w kodzie**: `patch("edceleste.ui.screens.app.widgets.app_header.datetime")` wystarcza | ✅ |
| 0.6 | `KeybindService(key_presser=...)`, domyślnie `pydirectinput`; testy dostają fake zapamiętujący klawisze | ✅ |
| 0.7 | Runner `pytest` (testy `unittest` działają bez zmian), marker `live_llm`, CI i dokumentacja zaktualizowane | ✅ |

Przy okazji: `voice_clone_modal_screen` używa `Provide[...]`, a nie był na liście
wiringu — działał tylko dlatego, że `widget_chatterbox_tts_settings_vertical`
go importuje. Teraz jest na liście jawnie.

---

## Faza 1 — scenariusze e2e UI (model skryptowany) 🚧

### Wspólny setup — fixture `edceleste` (`tests/e2e/conftest.py`)

Każdy test dostaje własny `tmp_path` z `config.yaml`, folderem journala i
bindings oraz prawdziwy `Container` podpięty do UI. Podmienione są tylko
krawędzie: config (`SettingsService(config_path=...)`), klawiatura
(`FakeKeyboard.keyboard_log`), okno gry (`FakeWindowsApiWithGameInFront`),
głośnik (`FakeTtsProvider` → `spoken_texts`) i LLM (`FunctionModel` przez
`use_scripted_model`; `ALLOW_MODEL_REQUESTS = False`). Testy to funkcje pytesta
z `pytestmark = pytest.mark.anyio` (plugin `anyio`, bez dodatkowych paczek).

```python
async def test_should_show_an_event_written_to_the_journal_in_the_ship_log(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        edceleste.append_journal_event("FSDJump")

        await edceleste.wait_until(
            pilot,
            lambda: "FSDJump" in ship_log_events(pilot.app),
            "FSDJump in the ship log",
        )
```

### Scenariusze

1. ✅ Boot happy path → Dashboard (`test_boot.py`).
2. ⬜ Boot z krytycznym błędem (brak folderu journala): `[!!]`, aplikacja nie idzie dalej.
3. 🟨 Dopisany `FSDJump` → wiersz w ship logu ✅ (`test_journal_to_ship_log.py`);
   ⬜ nawigacja i nagłówek zaktualizowane.
4. 🟨 COMMS: odpowiedź streamowana do COMMS i do TTS ✅ (`test_comms.py`);
   ⬜ THINKING/IDLE, tool call, błąd („LLM turn failed”).
5. ⬜ Reakcja na zdarzenie: event z włączoną reakcją → automatyczna odpowiedź.
6. ⬜ Settings: zmiana pola → wskaźnik modyfikacji → `ctrl+s` → SAVED, YAML w tmp
   zmieniony → `escape` wraca do Dashboardu.
7. ⬜ Settings z błędem walidacji: FAILED + komunikat w sekcji.
8. ⬜ `ctrl+e` rozwija/zwija ship log, z obsługą `ALWAYS_EXPANDED_TABS`.

### Wnioski z pierwszych testów

- `app.query()` szuka tylko na pierwszym ekranie — Dashboard jest wypychany
  na stos, więc w testach zawsze `app.screen.query(...)`.
- `unittest.IsolatedAsyncioTestCase` puszcza pętlę asyncio w trybie debug —
  test trwał ~5 s. Pod pytestem + `anyio` ten sam test trwa ~1 s.
- `app.workers.wait_for_complete()` wisi na Dashboardzie (workery streamują
  w nieskończoność) — stąd `wait_until`.
- Watcher czyta journal od końca (`seek(0, 2)`), więc eventy dopisujemy dopiero
  po starcie Dashboardu.
- Config testowy ma wszystkie `event_reactions` wyłączone — `LoadGame: true`
  wywołałby automatyczną odpowiedź LLM w środku scenariusza.
- `LLMService.test_connection` korzysta teraz z `build_model`, więc jedna
  podmiana obejmuje i PREFLIGHT, i rozmowę.
- **Bug w aplikacji (naprawiony):** `UIApp` wstrzykiwał Dashboardowi
  `game_watcher_service_stub`, więc przy wyjściu zatrzymywany był stub, a
  prawdziwy watcher dalej trzymał otwarty journal. Teraz `UIApp` dostaje
  `game_watcher_service`; pilnuje tego
  `test_should_stop_watching_the_journal_when_the_app_closes`.
- `TTSService.get_tts_voices` woła `edge_tts.list_voices()` (sieć) z pominięciem
  providera — przed scenariuszami Settings → TTS trzeba to podmienić.

### `FunctionModel` — jak to działa

`pydantic_ai.models.function.FunctionModel` to „model”, którego odpowiedzi pisze
się jako zwykłą funkcję. Funkcja dostaje `messages` (cała rozmowa, łącznie z
wynikami narzędzi) i `agent_info` (m.in. `function_tools`, `instructions`).
Udawany jest **tylko model** — walidacja argumentów narzędzia, wykonanie
`PerformGameAction.execute`, eventy (`PartStartEvent`/`PartEndEvent`) i nasze
`to_message_block` / `to_tool_call` / `to_tool_result` działają naprawdę.

`LLMService` używa `run_stream_events`, więc potrzebny jest `stream_function`
(async generator; w jednym wywołaniu albo same stringi, albo same `DeltaToolCall`):

```python
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


async def fake_pilot_model(messages, agent_info: AgentInfo):
    last_message_parts = messages[-1].parts
    tool_already_answered = any(
        isinstance(part, ToolReturnPart) for part in last_message_parts
    )

    if not tool_already_answered:
        # Krok 1: "model" prosi o wywołanie narzędzia
        yield {
            0: DeltaToolCall(
                name="perform_game_action",
                json_args='{"action": "LandingGearToggle"}',
            )
        }
    else:
        # Krok 2: narzędzie się wykonało, "model" odpowiada pilotowi
        yield "Landing gear "
        yield "deployed, Commander."


fake_model = FunctionModel(stream_function=fake_pilot_model)
```

Podpięcie: `Agent` w `LLMService` jest prywatny, więc podmieniamy `build_model`
(z niego korzysta `reload_service`) — system prompt i narzędzia budują się jak
w aplikacji:

```python
llm_service = container.llm_service()
llm_service.build_model = lambda provider: fake_model
```

Pokrewne:

- `pydantic_ai.models.test.TestModel` — automat: woła wszystkie narzędzia
  (albo `call_tools=[...]`) z argumentami ze schematu, zwraca
  `custom_output_text`. Dobry na „nic się nie wywala”, bez kontroli nad treścią.
- `pydantic_ai.models.ALLOW_MODEL_REQUESTS = False` — bezpiecznik: przypadkowe
  użycie prawdziwego modelu kończy się `RuntimeError`. Włączony we wszystkich
  testach poza `live_llm`.
- `Agent.override(model=...)` — oficjalna podmiana, gdy ma się dostęp do `Agent`.

---

## Faza 2 — żywy LLM (eksperyment)

### Konfiguracja

- Zmienne: `OPENROUTER_API_KEY`, `EDCELESTE_TEST_LLM_MODEL` (model w zmiennej,
  nie w kodzie — darmowe modele rotują).
- Model musi wspierać tool calling: `GET https://openrouter.ai/api/v1/models`,
  w `supported_parameters` musi być `tools`. Krok w `weekly_maintenance.yml`
  sprawdzający, czy wybrany model nadal jest dostępny i darmowy.
- Ustawienia prywatności konta OpenRouter: włączyć darmowe endpointy, które
  mogą logować prompty (inaczej zapytania są odrzucane).
- **Limity** (sprawdzić aktualne w dokumentacji OpenRoutera): darmowe modele mają
  limit dzienny (rzędu 50/dzień bez doładowania, ~1000/dzień po jednorazowym
  doładowaniu 10 $) i limit na minutę. Scenariusz z narzędziem = min. 2 zapytania,
  boot przez PREFLIGHT = +1 (`test_connection`). Doładowanie 10 $ prawie na pewno
  będzie potrzebne.

### A. Kontrakt `LLMService` + narzędzie (bez UI, tabela)

| Prompt | Oczekiwane |
|---|---|
| „Open the landing gear” | `ToolCall(perform_game_action, action=LandingGearToggle)` + klawisz z `test_binds.xml` w `pressed_keys` |
| „Wysuń podwozie” | to samo (prompt po polsku) |
| „Lights on” / „scoop cargo” | właściwy `EdAction` |
| „What's my fuel level?” | brak tool calla, `pressed_keys` puste |
| „Open the landing gear” przy `game_actions.enabled: false` | tool call, `ToolResult` z `is_error`, `pressed_keys` puste |

Asercje na **zachowaniu** (narzędzie, argument, klawisz), nie na treści odpowiedzi.
Ta warstwa łapie też regresje po zmianie system promptu albo docstringu
`PerformGameAction.execute` (docstring = opis narzędzia dla modelu).

### B. Złoty scenariusz przez całe UI

Boot → wpisanie „open the landing gear” w COMMS → Enter → w COMMS wiadomość
użytkownika i wpis o tool callu, stan wraca do IDLE, `FakeKeyPresser` dostał
klawisz. Cały łańcuch: UI → repozytorium → kolejka → pydantic-ai → OpenRouter
→ narzędzie → KeybindService → klawisz.

### Niedeterministyczność

- Marker `@pytest.mark.live_llm`. Lokalnie bez klucza → skip. W CI
  `EDCELESTE_REQUIRE_LIVE_LLM=1` → brak klucza = **fail**, nie cichy skip.
- „k z N”: np. 3 próby, zalicza przy 2 sukcesach; raport ze skutecznością.
- 429 / 5xx / timeout liczone osobno jako `infra_error`, nie jako błąd modelu.

### CI

- Osobny job `e2e-live-llm` po `test`, environment `pr-action`, sekret
  `OPENROUTER_API_KEY`. PR z forka / od dependabota (bez sekretów) → jawny skip.
- Pierwsze 2–3 tygodnie `continue-on-error: true`, mierzymy flakiness, potem
  decyzja o blokowaniu.
- Nocny run na `main` + `workflow_dispatch` z macierzą modeli — przy okazji
  ranking, które darmowe modele dobrze wołają narzędzia.

---

## Faza 3 — snapshoty SVG

- `pytest-textual-snapshot` (fixture `snap_compare` — pasuje do testów-funkcji
  pytesta z fazy 1), rozmiar 200×50 (siatka z makiet),
  `animation_level = "none"`, stały czas w nagłówku (patch `datetime`).
- PREFLIGHT (w trakcie / sukces / błąd), Dashboard (zwykły / rozwinięty, z
  eventami), każda sekcja Settings, modal klonowania głosu.
- Snapshoty generowane i porównywane na Linuksie (CI); `--snapshot-update`
  lokalnie, raport HTML z różnicami jako artefakt joba.

---

## Faza 4 — domknięcie

- Usunąć `*/ui/*` z `omit` w coverage.
- Sekcja w `CLAUDE.md`: `pytest -m "not live_llm"`, `pytest -m live_llm`,
  aktualizacja snapshotów.
