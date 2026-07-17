from protocols.settings_protocol import SettingsProtocol


class LoadSettingsUseCase:
    def __init__(self, settings_repository: SettingsProtocol):
        self.settings_repository = settings_repository

    def __call__(self):
        return self.settings_repository.load_settings()
