import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Switch

from edceleste.services.models.settings_model import (
    DEFAULT_EDGE_VOICE,
    ChatterboxParamsModel,
    EdgeParamsModel,
    PocketParamsModel,
    TTSModel,
)
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_tts_container import (
    ENGINE_NAMES,
    ENGINES_OF_LOCATION,
    WidgetTTSContainer,
    build_default_params_for_engine,
    find_location_of_engine,
)
from edceleste.ui.screens.settings.widgets.tts.widget_voice_test_button import (
    WidgetVoiceTestButton,
)

CONTAINER_MODULE = "edceleste.ui.screens.settings.widgets.tts.widget_tts_container"
CHATTERBOX_MODULE = (
    "edceleste.ui.screens.settings.widgets.tts.widget_chatterbox_tts_settings_vertical"
)
PROFILE_INPUT = "tts-profile-input"
ENGINE_INPUT = "tts-provider-type-input"
LOCATION_INPUT = "tts-location-input"
SHIP_EFFECT_INPUT = "ship-effect-input"


class StubProfiles(Vertical):
    """Stands in for the voice profiles block, which reads the disk. Only keeps
    the params it was made for."""

    def __init__(self, params, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.params = params


class SectionApp(App):
    def __init__(self, tts_model: TTSModel) -> None:
        super().__init__()
        self.tts_model = tts_model

    def compose(self) -> ComposeResult:
        yield WidgetTTSContainer(self.tts_model, id="settings-tts")


class RecordingSectionApp(SectionApp):
    """The same section, and it keeps every SectionSettingsChanged message the
    section posts."""

    def __init__(self, tts_model: TTSModel) -> None:
        super().__init__(tts_model)
        self.section_messages: list[SectionSettingsChanged] = []

    def on_section_settings_changed(self, message: SectionSettingsChanged) -> None:
        self.section_messages.append(message)


def make_pocket_model(profile: str = "voice_p") -> TTSModel:
    return TTSModel(
        provider="pocket",
        params=PocketParamsModel(type="pocket", profile=profile),
        volume=0.5,
    )


def make_chatterbox_model(profile: str = "voice_c") -> TTSModel:
    return TTSModel(
        provider="chatterbox",
        params=ChatterboxParamsModel(type="chatterbox", profile=profile),
        volume=0.5,
    )


def make_edge_model() -> TTSModel:
    return TTSModel(
        provider="edge",
        params=EdgeParamsModel(type="edge", voice="en-US-AriaNeural"),
        volume=0.5,
    )


class TestFindLocationOfEngine(unittest.TestCase):
    def test_pocket_tts_and_chatterbox_run_locally(self):
        self.assertEqual(find_location_of_engine("pocket"), "local")
        self.assertEqual(find_location_of_engine("chatterbox"), "local")

    def test_edge_runs_remotely(self):
        self.assertEqual(find_location_of_engine("edge"), "remote")

    def test_an_unknown_engine_raises_value_error(self):
        with self.assertRaises(ValueError):
            find_location_of_engine("piper")


class TestBuildDefaultParamsForEngine(unittest.TestCase):
    def test_pocket_gets_pocket_params_with_no_profile(self):
        params = build_default_params_for_engine("pocket")

        self.assertIsInstance(params, PocketParamsModel)
        self.assertEqual(params.profile, "")

    def test_chatterbox_gets_chatterbox_params_with_no_profile(self):
        params = build_default_params_for_engine("chatterbox")

        self.assertIsInstance(params, ChatterboxParamsModel)
        self.assertEqual(params.profile, "")

    def test_edge_gets_the_default_edge_voice(self):
        params = build_default_params_for_engine("edge")

        self.assertIsInstance(params, EdgeParamsModel)
        self.assertEqual(params.voice, DEFAULT_EDGE_VOICE)

    def test_every_engine_has_a_name_and_one_location(self):
        self.assertEqual(
            ENGINE_NAMES,
            {"edge": "Edge TTS", "chatterbox": "Chatterbox", "pocket": "Pocket TTS"},
        )
        self.assertEqual(
            ENGINES_OF_LOCATION,
            {"local": ["pocket", "chatterbox"], "remote": ["edge"]},
        )


class TestWidgetTTSContainer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for module in (CONTAINER_MODULE, CHATTERBOX_MODULE):
            patcher = patch(f"{module}.WidgetVoiceProfilesVertical", StubProfiles)
            patcher.start()
            self.addCleanup(patcher.stop)
        # The real Edge block asks the network for the list of voices
        edge_patcher = patch(
            f"{CONTAINER_MODULE}.WidgetEdgeTTSSettingsVertical", StubProfiles
        )
        edge_patcher.start()
        self.addCleanup(edge_patcher.stop)

    async def test_the_location_select_offers_local_and_remote_and_shows_local(
        self,
    ):
        app = SectionApp(make_pocket_model())

        async with app.run_test() as pilot:
            await pilot.pause()
            row = app.query_one(f"#{LOCATION_INPUT}", WidgetLabeledSelectRow)

            self.assertEqual(row.options, ["Local", "Remote"])
            self.assertEqual(row.values, ["local", "remote"])
            self.assertEqual(row.initial_value, "local")

    async def test_an_edge_model_shows_remote_and_only_edge_in_the_engine_select(self):
        app = SectionApp(make_edge_model())

        async with app.run_test() as pilot:
            await pilot.pause()
            location_row = app.query_one(f"#{LOCATION_INPUT}", WidgetLabeledSelectRow)
            engine_row = app.query_one(f"#{ENGINE_INPUT}", WidgetLabeledSelectRow)

            self.assertEqual(location_row.initial_value, "remote")
            self.assertEqual(engine_row.options, ["Edge TTS"])
            self.assertEqual(engine_row.values, ["edge"])
            self.assertEqual(engine_row.initial_value, "edge")

    async def test_switching_the_location_to_remote_gives_edge_with_the_default_voice(
        self,
    ):
        model = make_pocket_model()
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(LOCATION_INPUT, "remote")
            )
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(model.provider, "edge")
            self.assertIsInstance(model.params, EdgeParamsModel)
            self.assertEqual(model.params.voice, DEFAULT_EDGE_VOICE)
            engine_row = app.query_one(f"#{ENGINE_INPUT}", WidgetLabeledSelectRow)
            self.assertEqual(engine_row.values, ["edge"])

    async def test_switching_the_location_to_local_picks_pocket_tts_first(self):
        model = make_edge_model()
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(LOCATION_INPUT, "local")
            )
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(model.provider, "pocket")
            self.assertIsInstance(model.params, PocketParamsModel)
            self.assertEqual(model.params.profile, "")

    async def test_a_round_trip_through_remote_keeps_the_params_of_chatterbox(self):
        model = make_chatterbox_model("voice_c")
        chatterbox_params = model.params
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            container = app.query_one(WidgetTTSContainer)

            container.post_message(ValueChanged(LOCATION_INPUT, "remote"))
            await pilot.pause()
            await pilot.pause()
            container.post_message(ValueChanged(LOCATION_INPUT, "local"))
            await pilot.pause()
            await pilot.pause()
            container.post_message(ValueChanged(ENGINE_INPUT, "chatterbox"))
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(model.provider, "chatterbox")
            self.assertIs(model.params, chatterbox_params)
            self.assertEqual(model.params.profile, "voice_c")

    async def test_picking_the_location_that_is_already_shown_changes_nothing(self):
        model = make_chatterbox_model()
        chatterbox_params = model.params
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            container = app.query_one(WidgetTTSContainer)
            # Called directly and checked at once: a message that waits in the
            # queue could be fixed by a late event of the old selects
            container.on_value_changed(ValueChanged(LOCATION_INPUT, "local"))

            self.assertEqual(model.provider, "chatterbox")
            self.assertIs(model.params, chatterbox_params)
            self.assertFalse(container.is_modified())

    async def test_a_blank_location_is_ignored(self):
        model = make_pocket_model()
        pocket_params = model.params
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(LOCATION_INPUT, "Select.NULL")
            )
            await pilot.pause()

            self.assertEqual(model.provider, "pocket")
            self.assertIs(model.params, pocket_params)

    async def test_a_blank_engine_is_ignored(self):
        model = make_pocket_model()
        pocket_params = model.params
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(ENGINE_INPUT, "Select.NULL")
            )
            await pilot.pause()

            self.assertEqual(model.provider, "pocket")
            self.assertIs(model.params, pocket_params)

    async def test_the_engine_select_offers_the_local_engines_and_shows_the_saved_one(
        self,
    ):
        app = SectionApp(make_pocket_model())

        async with app.run_test() as pilot:
            await pilot.pause()
            row = app.query_one(f"#{ENGINE_INPUT}", WidgetLabeledSelectRow)

            self.assertEqual(row.options, ["Pocket TTS", "Chatterbox"])
            self.assertEqual(row.values, ["pocket", "chatterbox"])
            self.assertEqual(row.initial_value, "pocket")

    async def test_pocket_shows_the_voice_profiles_and_no_chatterbox_params(self):
        model = make_pocket_model()
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()

            profiles = app.query(StubProfiles)
            self.assertEqual(len(profiles), 1)
            self.assertIs(profiles.first().params, model.params)
            self.assertEqual(len(app.query("#tts-exaggeration-input")), 0)
            self.assertEqual(len(app.query("#tts-nano-input")), 0)

    async def test_chatterbox_shows_the_voice_profiles_and_its_own_params(self):
        model = make_chatterbox_model()
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()

            profiles = app.query(StubProfiles)
            self.assertEqual(len(profiles), 1)
            self.assertIs(profiles.first().params, model.params)
            self.assertEqual(len(app.query("#tts-exaggeration-input")), 1)
            self.assertEqual(len(app.query("#tts-nano-input")), 1)

    async def test_picking_a_profile_writes_it_into_the_pocket_params(self):
        model = make_pocket_model("voice_p")
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(PROFILE_INPUT, "wingman")
            )
            await pilot.pause()

        self.assertEqual(model.params.profile, "wingman")

    async def test_picking_a_profile_writes_it_into_the_chatterbox_params(self):
        model = make_chatterbox_model("voice_c")
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(PROFILE_INPUT, "wingman")
            )
            await pilot.pause()

        self.assertEqual(model.params.profile, "wingman")

    async def test_switching_to_pocket_gives_pocket_params_with_no_profile(self):
        model = make_chatterbox_model()
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(ENGINE_INPUT, "pocket")
            )
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(model.provider, "pocket")
            self.assertIsInstance(model.params, PocketParamsModel)
            self.assertEqual(model.params.profile, "")
            self.assertEqual(len(app.query("#tts-exaggeration-input")), 0)

    async def test_switching_back_and_forth_keeps_the_params_of_each_engine(self):
        model = make_chatterbox_model("voice_c")
        chatterbox_params = model.params
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            container = app.query_one(WidgetTTSContainer)

            container.post_message(ValueChanged(ENGINE_INPUT, "pocket"))
            await pilot.pause()
            await pilot.pause()
            container.post_message(ValueChanged(PROFILE_INPUT, "voice_p"))
            await pilot.pause()
            container.post_message(ValueChanged(ENGINE_INPUT, "chatterbox"))
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(model.provider, "chatterbox")
            self.assertIs(model.params, chatterbox_params)
            self.assertEqual(model.params.profile, "voice_c")

            container.post_message(ValueChanged(ENGINE_INPUT, "pocket"))
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(model.provider, "pocket")
            self.assertEqual(model.params.profile, "voice_p")

    async def test_switching_the_engine_marks_the_section_as_modified(self):
        app = SectionApp(make_chatterbox_model())

        async with app.run_test() as pilot:
            await pilot.pause()
            container = app.query_one(WidgetTTSContainer)
            self.assertFalse(container.is_modified())

            container.post_message(ValueChanged(ENGINE_INPUT, "pocket"))
            await pilot.pause()
            await pilot.pause()

            self.assertTrue(container.is_modified())

    async def test_a_profile_message_leaves_edge_params_alone(self):
        model = TTSModel(
            provider="edge",
            params=EdgeParamsModel(type="edge", voice="en-US-AriaNeural"),
            volume=0.5,
        )
        app = SectionApp(model)

        with patch(f"{CONTAINER_MODULE}.WidgetEdgeTTSSettingsVertical", StubProfiles):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.query_one(WidgetTTSContainer).post_message(
                    ValueChanged(PROFILE_INPUT, "wingman")
                )
                await pilot.pause()

        self.assertEqual(model.params.voice, "en-US-AriaNeural")

    # --- the ship effect switch ---

    async def test_the_ship_effect_switch_shows_the_saved_value_when_it_is_on(self):
        model = make_pocket_model()
        model.ship_effect = True
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            row = app.query_one(f"#{SHIP_EFFECT_INPUT}", WidgetLabeledSwitchRow)

            self.assertIs(row.value, True)
            self.assertIs(row.query_one(Switch).value, True)

    async def test_the_ship_effect_switch_shows_the_saved_value_when_it_is_off(self):
        model = make_pocket_model()
        model.ship_effect = False
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            row = app.query_one(f"#{SHIP_EFFECT_INPUT}", WidgetLabeledSwitchRow)

            self.assertIs(row.value, False)
            self.assertIs(row.query_one(Switch).value, False)

    async def test_the_ship_effect_switch_is_shown_for_every_engine(self):
        for make_model in (make_pocket_model, make_chatterbox_model, make_edge_model):
            with self.subTest(engine=make_model.__name__):
                app = SectionApp(make_model())

                async with app.run_test() as pilot:
                    await pilot.pause()

                    self.assertEqual(len(app.query(f"#{SHIP_EFFECT_INPUT}")), 1)

    async def test_the_test_voice_button_is_shown_last_for_every_engine(self):
        for make_model in (make_pocket_model, make_chatterbox_model, make_edge_model):
            with self.subTest(engine=make_model.__name__):
                model = make_model()
                app = SectionApp(model)

                async with app.run_test() as pilot:
                    await pilot.pause()

                    test_buttons = app.query(WidgetVoiceTestButton)
                    self.assertEqual(len(test_buttons), 1)
                    self.assertIs(test_buttons.first().tts_model, model)
                    last_row = (
                        app.query_one(WidgetTTSContainer)
                        .query_one(VerticalScroll)
                        .children[-1]
                    )
                    self.assertIs(last_row, test_buttons.first())

    async def test_switching_the_ship_effect_writes_it_into_the_model(self):
        model = make_pocket_model()
        model.ship_effect = True
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            switch = app.query_one(f"#{SHIP_EFFECT_INPUT}").query_one(Switch)
            switch.value = False
            await pilot.pause()

            self.assertIs(model.ship_effect, False)

            switch.value = True
            await pilot.pause()

            self.assertIs(model.ship_effect, True)

    async def test_switching_the_ship_effect_posts_the_section_changed_message(self):
        model = make_pocket_model()
        app = RecordingSectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            messages_before_the_switch = len(app.section_messages)
            app.query_one(f"#{SHIP_EFFECT_INPUT}").query_one(Switch).toggle()
            await pilot.pause()

        self.assertEqual(len(app.section_messages), messages_before_the_switch + 1)
        self.assertIs(app.section_messages[-1].section, SettingsSection.TTS)
        self.assertIs(app.section_messages[-1].new_value, model)

    async def test_switching_the_ship_effect_marks_the_section_as_modified(self):
        app = SectionApp(make_pocket_model())

        async with app.run_test() as pilot:
            await pilot.pause()
            container = app.query_one(WidgetTTSContainer)
            self.assertFalse(container.is_modified())

            app.query_one(f"#{SHIP_EFFECT_INPUT}").query_one(Switch).toggle()
            await pilot.pause()

            self.assertTrue(container.is_modified())

    async def test_a_ship_effect_message_leaves_the_engine_params_alone(self):
        model = make_pocket_model("voice_p")
        app = SectionApp(model)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(WidgetTTSContainer).post_message(
                ValueChanged(SHIP_EFFECT_INPUT, False)
            )
            await pilot.pause()

        self.assertEqual(model.params.profile, "voice_p")
        self.assertEqual(model.provider, "pocket")
        self.assertIs(model.ship_effect, False)


if __name__ == "__main__":
    unittest.main()
