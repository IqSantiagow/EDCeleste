from textual.widget import Widget


class WidgetSettingsRow(Widget):
    """
    A generic class holding input widgets for specific settings and holding
    a generic validation methods to handle

    """

    def notify_about_validation_failure(self, error_message: str) -> None: ...

    def reset_validation_state(self) -> None: ...
