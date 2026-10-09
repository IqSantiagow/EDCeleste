from pydantic import BaseModel
from textual.message import Message
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection


class SectionSettingsChanged(Message):
    def __init__(self, section: SettingsSection, new_value: BaseModel) -> None:
        """Posted by a settings section container every time one of its inputs
        changes. SettingsScreen receives it and puts new_value into its
        unsaved settings copy. Nothing is saved here.

        Fails fast instead of letting a wrong section reach the screen:
        - ValueError when section or new_value is None,
        - TypeError when new_value is not the model class of that section,
          e.g. a TTSModel sent for SettingsSection.LLM.
        """
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
