import allure
import httpx
import pytest
from pydantic_ai import ModelHTTPError
from textual.app import App
from textual.widgets import Label

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from edceleste.ui.screens.system_check.system_check_screen import SystemCheckScreen
from tests.e2e.conftest import (
    answer_preflight_connection_test,
    comms_entries,
    open_settings_section,
    open_stt_settings,
    send_comms_message,
)
from tests.e2e.test_boot import preflight_row
from tests.e2e.test_push_to_talk_hotkey import (
    hold_and_release,
    save_settings_with_ctrl_s,
)
from tests.e2e.test_settings_llm import (
    CONNECTED,
    connection_result,
    model_list_is_shown,
)
from tests.e2e.test_streaming_voice import chatterbox_settings
from tests.e2e.test_voice_profiles import notification_texts, write_voice_profile_files

pytestmark = [pytest.mark.anyio, allure.feature("Service status dots in the header")]

LLM_DOT = "#stat-llm"
TTS_DOT = "#stat-tts"
MIC_DOT = "#stat-mic"
JOURNAL_DOT = "#stat-journal"
ALL_DOTS = [LLM_DOT, TTS_DOT, MIC_DOT, JOURNAL_DOT]

API_KEY = "sk-secret-test-key"


def dot_state(app: App, dot_id: str) -> str | None:
    """'ok' (green), 'off' (dim) or 'error' (red), None while it is not painted"""
    dot = app.screen.query_one(dot_id, Label)
    for state in ("ok", "off", "error"):
        if dot.has_class(f"-{state}"):
            return state
    return None


def dot_text(app: App, dot_id: str) -> str:
    return str(app.screen.query_one(dot_id, Label).content)


def dot_reason(app: App, dot_id: str) -> str:
    return str(app.screen.query_one(dot_id, Label).tooltip)


def all_dots_are_painted(app: App) -> bool:
    return all(dot_state(app, dot_id) is not None for dot_id in ALL_DOTS)


async def answer_copy_that(messages, agent_info):
    yield "Copy that, Commander."


def reject_the_key(messages, agent_info):
    raise ModelHTTPError(
        status_code=401,
        model_name="test-model",
        body={"error": {"message": f"Incorrect API key provided: {API_KEY}"}},
    )


@allure.title("When everything is configured the header shows four green dots")
async def test_should_show_four_green_dots_when_everything_works(edceleste):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("Then LLM, TTS, MIC and JRNL show a green filled dot"):
            await edceleste.wait_until(
                pilot,
                lambda: all_dots_are_painted(pilot.app),
                "the four dots in the header",
            )
            for dot_id, text in [
                (LLM_DOT, "● LLM"),
                (TTS_DOT, "● TTS"),
                (MIC_DOT, "● MIC"),
                (JOURNAL_DOT, "● JRNL"),
            ]:
                assert dot_text(pilot.app, dot_id) == text
                assert dot_state(pilot.app, dot_id) == "ok"

        with allure.step("And hovering a dot explains in plain words why it is green"):
            assert dot_reason(pilot.app, LLM_DOT) == "The LLM answered"
            assert dot_reason(pilot.app, TTS_DOT) == "Nothing played yet"
            assert dot_reason(pilot.app, MIC_DOT) == "Speech-to-text is on"
            assert dot_reason(pilot.app, JOURNAL_DOT) == "Watching the journal folder"

        with allure.step("And JRNL stays green although the journal is empty"):
            assert edceleste.journal_file.read_text() == ""
            assert dot_state(pilot.app, JOURNAL_DOT) == "ok"


@allure.title("A wrong LLM key shows the LLM dot red when Celeste starts")
async def test_should_show_the_llm_dot_red_when_the_provider_rejects_the_key(
    edceleste,
):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the LLM key in config.yaml is a wrong one"):
        edceleste.settings.llm.provider.api_key = API_KEY
        edceleste.save_config()

    with allure.step("And the provider answers HTTP 401 to the first test request"):
        edceleste.use_scripted_model(
            answer_copy_that, preflight_function=reject_the_key
        )

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the dashboard still opens"):
                await edceleste.open_dashboard(pilot, step_keyword="And")
                assert isinstance(pilot.app.screen, DashboardScreen)

            with allure.step("And the LLM dot is red"):
                await edceleste.wait_until(
                    pilot,
                    lambda: dot_state(pilot.app, LLM_DOT) == "error",
                    "the LLM dot red",
                )
                assert dot_text(pilot.app, LLM_DOT) == "● LLM"

            with allure.step("And hovering it shows the 401 but not the API key"):
                reason = dot_reason(pilot.app, LLM_DOT)
                assert "HTTP 401" in reason
                assert "Incorrect API key provided" in reason
                assert API_KEY not in reason
                assert "[REDACTED API KEY]" in reason

            with allure.step("And TTS, MIC and JRNL are green"):
                for dot_id in [TTS_DOT, MIC_DOT, JOURNAL_DOT]:
                    assert dot_state(pilot.app, dot_id) == "ok"


@allure.title("A failed LLM request turns the LLM dot red, the next good one green")
async def test_should_turn_the_llm_dot_red_then_green_around_a_failed_request(
    edceleste,
):
    connection_is_down = True

    async def answer_unless_the_connection_is_down(messages, agent_info):
        if connection_is_down:
            raise ConnectionError("Provider is down")
        yield "Copy that, Commander."

    with allure.step("Given the LLM connection is down"):
        edceleste.use_scripted_model(answer_unless_the_connection_is_down)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the LLM dot is green"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "ok",
                "the LLM dot green",
            )

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the LLM dot turns red and says the request failed"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "error",
                "the LLM dot red",
            )
            assert dot_reason(pilot.app, LLM_DOT) == (
                "The last request failed: Provider is down"
            )

        with allure.step("When the connection is back"):
            connection_is_down = False

        with allure.step("And the Commander sends 'again' in COMMS"):
            await send_comms_message(pilot, "again")

        with allure.step("Then Celeste answers in COMMS"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer after the failed request",
            )

        with allure.step("And the LLM dot is green again and says the request worked"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "ok",
                "the LLM dot green again",
            )
            assert dot_reason(pilot.app, LLM_DOT) == "The last request succeeded"


@allure.title("A rejected API key is hidden in the LLM dot and in COMMS")
async def test_should_hide_the_api_key_when_the_provider_rejects_a_message(edceleste):
    async def reject_the_chat_request(messages, agent_info):
        raise ModelHTTPError(
            status_code=401,
            model_name="test-model",
            body={"error": {"message": f"Incorrect API key provided: {API_KEY}"}},
        )
        yield

    with allure.step("Given the LLM key in config.yaml is a wrong one"):
        edceleste.settings.llm.provider.api_key = API_KEY
        edceleste.save_config()

    with allure.step("And the provider rejects every message with HTTP 401"):
        edceleste.use_scripted_model(reject_the_chat_request)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the LLM dot turns red and shows the 401"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "error",
                "the LLM dot red",
            )
            reason = dot_reason(pilot.app, LLM_DOT)
            assert reason.startswith("The last request failed:")
            assert "401" in reason
            assert "Incorrect API key provided" in reason

        with allure.step("And the LLM dot does not show the API key"):
            assert API_KEY not in reason
            assert "[REDACTED API KEY]" in reason

        with allure.step("And the SYSTEM line in COMMS says the turn failed"):
            await edceleste.wait_until(
                pilot,
                lambda: any(
                    line.startswith("LLM turn failed:")
                    for line in comms_entries(pilot.app, "system-message")
                ),
                "the failed turn in COMMS",
            )

        with allure.step("And the SYSTEM line does not show the API key"):
            failed_line = next(
                line
                for line in comms_entries(pilot.app, "system-message")
                if line.startswith("LLM turn failed:")
            )
            assert API_KEY not in failed_line
            assert "[REDACTED API KEY]" in failed_line


@allure.title("A request that times out names the problem in the LLM dot and in COMMS")
async def test_should_name_the_problem_when_a_request_fails_with_an_empty_error_text(
    edceleste,
):
    async def time_out_without_a_message(messages, agent_info):
        raise httpx.ReadTimeout("")
        yield

    with allure.step("Given the LLM provider times out without any error text"):
        edceleste.use_scripted_model(time_out_without_a_message)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the LLM dot turns red and names the timeout"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "error",
                "the LLM dot red",
            )
            assert dot_reason(pilot.app, LLM_DOT) == (
                "The last request failed: ReadTimeout"
            )

        with allure.step("And COMMS shows that the turn failed because of the timeout"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    "LLM turn failed: ReadTimeout"
                    in comms_entries(pilot.app, "system-message")
                ),
                "the timeout named in the failed turn in COMMS",
            )


@allure.title("A voice that breaks while speaking turns the TTS dot red")
async def test_should_turn_the_tts_dot_red_when_the_voice_breaks_then_green(
    edceleste,
):
    with allure.step("Given Chatterbox on a GPU is saved with the voice 'narrator'"):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(chatterbox_settings(device="cuda"))
        chatterbox = edceleste.fake_tts_providers["chatterbox"]

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the voice engine breaks once while speaking"):
            chatterbox.break_the_voice_once()

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the TTS dot turns red and says Celeste could not speak"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, TTS_DOT) == "error",
                "the TTS dot red",
            )
            assert dot_reason(pilot.app, TTS_DOT) == (
                "Celeste could not speak: CUDA out of memory"
            )

        with allure.step("And the Commander sends 'again' in COMMS"):
            await send_comms_message(pilot, "again")

        with allure.step(
            "Then the TTS dot is green again and says the speech was played"
        ):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, TTS_DOT) == "ok",
                "the TTS dot green again",
            )
            assert dot_reason(pilot.app, TTS_DOT) == "The last speech was played"


@allure.title("A microphone that cannot be opened turns the MIC dot red")
async def test_should_turn_the_mic_dot_red_when_the_microphone_cannot_be_opened(
    edceleste,
):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the microphone cannot be opened"):
        edceleste.microphone.cannot_be_opened("Error querying device -1")

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the MIC dot is green"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, MIC_DOT) == "ok",
                "the MIC dot green",
            )

        with allure.step("When the Commander holds F9 and lets go of it"):
            await hold_and_release(edceleste, "Key.f9")

        with allure.step("Then the MIC dot turns red and says why"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, MIC_DOT) == "error",
                "the MIC dot red",
            )
            assert dot_text(pilot.app, MIC_DOT) == "● MIC"
            assert dot_reason(pilot.app, MIC_DOT).startswith(
                "The microphone cannot be opened:"
            )
            assert "Error querying device -1" in dot_reason(pilot.app, MIC_DOT)

        with allure.step("And LLM, TTS and JRNL stay green"):
            for dot_id in [LLM_DOT, TTS_DOT, JOURNAL_DOT]:
                assert dot_state(pilot.app, dot_id) == "ok"


@allure.title("Switching speech to text off in Settings dims the MIC dot")
async def test_should_dim_the_mic_dot_when_speech_to_text_is_switched_off_in_settings(
    edceleste,
):
    with allure.step("Given speech to text is on and no push-to-talk key is set"):
        edceleste.turn_speech_to_text_on(None)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("And the MIC dot is green"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, MIC_DOT) == "ok",
                "the MIC dot green",
            )

        with allure.step("And the Commander opens Settings > Speech to text"):
            await open_stt_settings(edceleste, pilot)

        with allure.step("When the Commander switches speech to text off and saves"):
            await pilot.click("#stt-enabled-input Switch")
            await save_settings_with_ctrl_s(edceleste, pilot)

        with allure.step("Then the header of Settings shows MIC as an empty circle"):
            assert isinstance(pilot.app.screen, SettingsScreen)
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, MIC_DOT) == "off",
                "the MIC dot dim in the Settings header",
            )
            assert dot_text(pilot.app, MIC_DOT) == "○ MIC"
            assert dot_reason(pilot.app, MIC_DOT) == (
                "Speech-to-text is switched off in settings"
            )

        with allure.step("When the Commander presses Escape"):
            await pilot.press("escape")

        with allure.step(
            "Then the header of the dashboard shows MIC as an empty circle"
        ):
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, DashboardScreen),
                "the dashboard",
            )
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, MIC_DOT) == "off",
                "the MIC dot dim in the dashboard header",
            )
            assert dot_text(pilot.app, MIC_DOT) == "○ MIC"


@allure.title("A blank LLM answer is not spoken and the TTS dot stays green")
async def test_should_not_speak_a_blank_llm_answer_and_keep_the_tts_dot_green(
    edceleste,
):
    answers = ["   \n  ", "Copy that, Commander."]

    async def answer_blank_first_then_copy_that(messages, agent_info):
        yield answers.pop(0)

    with allure.step("Given the LLM answers only spaces and a new line the first time"):
        edceleste.use_scripted_model(answer_blank_first_then_copy_that)

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander sends 'hello' in COMMS"):
            await send_comms_message(pilot, "hello")

        with allure.step("Then the LLM finishes the request"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_reason(pilot.app, LLM_DOT) == "The last request succeeded",
                "the LLM request finished",
            )

        with allure.step("And the voice engine was asked to say nothing"):
            assert edceleste.spoken_texts == []

        with allure.step("And the TTS dot is green and nothing played yet"):
            assert dot_state(pilot.app, TTS_DOT) == "ok"
            assert dot_reason(pilot.app, TTS_DOT) == "Nothing played yet"

        with allure.step("When the Commander sends 'again' in COMMS"):
            await send_comms_message(pilot, "again")

        with allure.step("Then Celeste speaks the next, normal answer"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_reason(pilot.app, TTS_DOT) == "The last speech was played",
                "the normal answer played",
            )
            assert edceleste.spoken_texts == ["Copy that, Commander."]

        with allure.step("And the TTS dot is green"):
            assert dot_state(pilot.app, TTS_DOT) == "ok"


@allure.title("A passing Test connection in Settings turns the red LLM dot green")
async def test_should_turn_the_llm_dot_green_when_test_connection_passes(edceleste):
    key_is_accepted = False

    def reject_the_key_until_it_is_fixed(messages, agent_info):
        if key_is_accepted:
            return answer_preflight_connection_test(messages, agent_info)
        return reject_the_key(messages, agent_info)

    with allure.step("Given the LLM key in config.yaml is a wrong one"):
        edceleste.settings.llm.provider.api_key = API_KEY
        edceleste.save_config()

    with allure.step("And the provider rejects the key with HTTP 401"):
        edceleste.use_scripted_model(
            answer_copy_that, preflight_function=reject_the_key_until_it_is_fixed
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And the LLM dot is red"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "error",
                "the LLM dot red",
            )

        with allure.step("And the Commander opens Settings > LLM"):
            await open_settings_section(edceleste, pilot, "settings-llm")
            await edceleste.wait_until(
                pilot, lambda: model_list_is_shown(pilot.app), "the list of LLM models"
            )

        with allure.step("And the provider now accepts the key"):
            key_is_accepted = True

        with allure.step("When the Commander presses Test connection"):
            await edceleste.click_when_ready(pilot, "#test-connection-button")

        with allure.step("Then Test connection shows Connected"):
            await edceleste.wait_until(
                pilot, lambda: connection_result(pilot.app) == CONNECTED, "Connected"
            )

        with allure.step("And the LLM dot in the Settings header is green"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "ok",
                "the LLM dot green",
            )
            assert dot_reason(pilot.app, LLM_DOT) == "The LLM answered"

        with allure.step("When the Commander presses Escape"):
            await pilot.press("escape")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, DashboardScreen),
                "the dashboard",
            )

        with allure.step("Then the LLM dot on the dashboard is green"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "ok",
                "the LLM dot green on the dashboard",
            )


@allure.title("A failing Test connection in Settings leaves the LLM dot red")
async def test_should_keep_the_llm_dot_red_when_test_connection_fails(edceleste):
    with allure.step("Given the LLM key in config.yaml is a wrong one"):
        edceleste.settings.llm.provider.api_key = API_KEY
        edceleste.save_config()

    with allure.step("And the provider rejects the key with HTTP 401"):
        edceleste.use_scripted_model(
            answer_copy_that, preflight_function=reject_the_key
        )

    async with edceleste.run_app() as pilot:
        await edceleste.open_dashboard(pilot, step_keyword="And")

        with allure.step("And the LLM dot is red"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, LLM_DOT) == "error",
                "the LLM dot red",
            )

        with allure.step("And the Commander opens Settings > LLM"):
            await open_settings_section(edceleste, pilot, "settings-llm")
            await edceleste.wait_until(
                pilot, lambda: model_list_is_shown(pilot.app), "the list of LLM models"
            )

        with allure.step("When the Commander presses Test connection"):
            await edceleste.click_when_ready(pilot, "#test-connection-button")

        with allure.step("Then Test connection shows the HTTP 401 failure"):
            await edceleste.wait_until(
                pilot,
                lambda: "HTTP 401" in connection_result(pilot.app),
                "the failure of Test connection",
            )
            assert connection_result(pilot.app).startswith("✗")
            assert API_KEY not in connection_result(pilot.app)

        with allure.step("And the LLM dot is still red and names the HTTP 401"):
            assert dot_state(pilot.app, LLM_DOT) == "error"
            assert "HTTP 401" in dot_reason(pilot.app, LLM_DOT)
            assert API_KEY not in dot_reason(pilot.app, LLM_DOT)


@allure.title(
    "A Whisper that cannot be loaded fails the STT check and turns the MIC dot red"
)
async def test_should_show_stt_failed_and_the_mic_dot_red_when_whisper_cannot_be_loaded(
    edceleste,
    monkeypatch,
):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the preflight stays open one second so it can be read"):
        monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 1)

    with allure.step("And Whisper cannot be loaded"):
        edceleste.microphone.whisper_cannot_be_loaded("Whisper model file is corrupted")

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step(
                "Then the STT row of the preflight is failed with the reason"
            ):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "stt").state == "failed",
                    "the STT row of the preflight marked as failed",
                )
                assert (
                    preflight_row(pilot.app, "stt").error_message
                    == "Whisper model file is corrupted"
                )

            await edceleste.open_dashboard(pilot, step_keyword="And")

            with allure.step("And the MIC dot is red with the same reason"):
                await edceleste.wait_until(
                    pilot,
                    lambda: dot_state(pilot.app, MIC_DOT) == "error",
                    "the MIC dot red",
                )
                assert dot_text(pilot.app, MIC_DOT) == "● MIC"
                assert (
                    dot_reason(pilot.app, MIC_DOT) == "Whisper model file is corrupted"
                )

            with allure.step("And the other dots are not red"):
                for dot_id in [LLM_DOT, TTS_DOT, JOURNAL_DOT]:
                    assert dot_state(pilot.app, dot_id) != "error"


@allure.title(
    "A voice that fails while warming up fails the TTS check and turns the TTS dot red"
)
async def test_should_show_tts_failed_and_the_dot_red_when_the_voice_fails_to_warm_up(
    edceleste,
    monkeypatch,
):
    with allure.step("Given Chatterbox on a GPU is saved with the voice 'narrator'"):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(chatterbox_settings(device="cuda"))

    with allure.step("And speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the preflight stays open one second so it can be read"):
        monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 1)

    with allure.step("And the voice engine runs out of memory while warming up"):
        edceleste.fake_tts_providers["chatterbox"].break_the_warm_up(
            "CUDA out of memory"
        )

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step(
                "Then the TTS row of the preflight is failed with the reason"
            ):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "tts").state == "failed",
                    "the TTS row of the preflight marked as failed",
                )
                assert (
                    preflight_row(pilot.app, "tts").error_message
                    == "CUDA out of memory"
                )

            await edceleste.open_dashboard(pilot, step_keyword="And")

            with allure.step("And the TTS dot is red with the same reason"):
                await edceleste.wait_until(
                    pilot,
                    lambda: dot_state(pilot.app, TTS_DOT) == "error",
                    "the TTS dot red",
                )
                assert dot_text(pilot.app, TTS_DOT) == "● TTS"
                assert dot_reason(pilot.app, TTS_DOT) == "CUDA out of memory"

            with allure.step("And the other dots are not red"):
                for dot_id in [LLM_DOT, MIC_DOT, JOURNAL_DOT]:
                    assert dot_state(pilot.app, dot_id) != "error"


@allure.title(
    "A failed transcription after the push-to-talk key shows a toast and a red "
    "MIC dot until the next recording"
)
async def test_should_show_a_toast_and_a_red_mic_dot_when_whisper_fails_on_the_hotkey(
    edceleste,
):
    with allure.step("Given speech to text is on and F9 is the push-to-talk key"):
        edceleste.turn_speech_to_text_on("Key.f9")

    with allure.step("And the microphone hears 'Request docking'"):
        edceleste.microphone.hears("Request docking")

    with allure.step("And the LLM answers 'Copy that, Commander.'"):
        edceleste.use_scripted_model(answer_copy_that)

    with allure.step("And Whisper fails while turning the recording into text"):
        edceleste.microphone.whisper_fails("Whisper ran out of memory")

    async with edceleste.run_app(show_notifications=True) as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander holds F9, speaks and lets go of it"):
            await hold_and_release(edceleste, "Key.f9")

        with allure.step("Then a toast says the speech to text failed and why"):
            await edceleste.wait_until(
                pilot,
                lambda: any(
                    "STT error: Whisper ran out of memory" in text
                    for text in notification_texts(pilot.app)
                ),
                "the toast with the speech to text error",
            )

        with allure.step("And the MIC dot is red with the same reason"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, MIC_DOT) == "error",
                "the MIC dot red",
            )
            assert dot_reason(pilot.app, MIC_DOT) == (
                "Speech-to-text failed: Whisper ran out of memory"
            )

        with allure.step("And nothing was sent to COMMS"):
            assert comms_entries(pilot.app, "user-command") == []

        with allure.step("And Whisper works again"):
            edceleste.microphone.whisper_works_again()

        with allure.step("When the Commander holds F9, speaks and lets go of it again"):
            await hold_and_release(edceleste, "Key.f9")

        with allure.step("Then COMMS shows the spoken command and the answer"):
            await edceleste.wait_until(
                pilot,
                lambda: comms_entries(pilot.app, "llm-response") != [],
                "Celeste's answer in COMMS",
            )
            assert comms_entries(pilot.app, "user-command") == ["Request docking"]

        with allure.step("And the MIC dot is green again"):
            assert dot_state(pilot.app, MIC_DOT) == "ok"

        with allure.step("And Celeste has finished answering"):
            await edceleste.wait_until(
                pilot,
                lambda: pilot.app.screen.query_one(
                    "#comms-thinking-indicator"
                ).has_class("hidden"),
                "the thinking indicator hidden",
            )


@allure.title(
    "A failed transcription after the mic button shows a toast and a red MIC dot"
)
async def test_should_show_a_toast_and_a_red_mic_dot_when_whisper_fails_on_the_button(
    edceleste,
):
    with allure.step("Given speech to text is on and no push-to-talk key is set"):
        edceleste.turn_speech_to_text_on(None)

    with allure.step("And Whisper fails while turning the recording into text"):
        edceleste.microphone.whisper_fails("Whisper ran out of memory")

    async with edceleste.run_app(show_notifications=True) as pilot:
        await edceleste.boot_to_dashboard(pilot, step_keyword="And")

        with allure.step("When the Commander holds the mic button and lets go of it"):
            await pilot.mouse_down("#comms-stt-button")
            await pilot.mouse_up("#comms-stt-button")

        with allure.step("Then a toast says the speech to text failed and why"):
            await edceleste.wait_until(
                pilot,
                lambda: any(
                    "STT error: Whisper ran out of memory" in text
                    for text in notification_texts(pilot.app)
                ),
                "the toast with the speech to text error",
            )

        with allure.step("And the MIC dot is red with the same reason"):
            await edceleste.wait_until(
                pilot,
                lambda: dot_state(pilot.app, MIC_DOT) == "error",
                "the MIC dot red",
            )
            assert dot_reason(pilot.app, MIC_DOT) == (
                "Speech-to-text failed: Whisper ran out of memory"
            )
