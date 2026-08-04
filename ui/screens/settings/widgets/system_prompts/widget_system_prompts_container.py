from textual.app import ComposeResult
from textual.containers import Vertical

from services.models.settings_model import LLMModel
from ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetSystemPromptsContainer(Vertical):
    def __init__(self, llm_model: LLMModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.llm_model = llm_model

    def compose(self) -> ComposeResult:
        yield WidgetSectionHeader("LLM SETTINGS")
