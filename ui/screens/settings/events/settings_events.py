from pydantic import BaseModel
from textual.message import Message
from ui.screens.settings.widgets.const_ids import SettingsSection


class SectionSettingsChanged(Message):
    def __init__(self, section: SettingsSection, new_value: BaseModel) -> None:
        super().__init__()
        self.section = section
        self.new_value = new_value
        assert section is not None, "SectionSettingsChanged message must have a section"
        assert new_value is not None, (
            "SectionSettingsChanged message must have a new_value"
        )
        assert isinstance(new_value, section.value), (
            "SectionSettingsChanged message new_value must be an instance of "
            "the section's model class"
        )
