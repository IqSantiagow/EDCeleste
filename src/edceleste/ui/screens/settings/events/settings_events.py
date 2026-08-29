from pydantic import BaseModel
from textual.message import Message
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection


class SectionSettingsChanged(Message):
    def __init__(self, section: SettingsSection, new_value: BaseModel) -> None:
        super().__init__()
        self.section = section
        self.new_value = new_value
        if section is None:
            raise ValueError("SectionSettingsChanged message must have a section")
        if new_value is None:
            raise ValueError("SectionSettingsChanged message must have a new_value")
        if not isinstance(new_value, section.value):
            raise TypeError(
                "SectionSettingsChanged message new_value must be an instance of "
                "the section's model class"
            )
