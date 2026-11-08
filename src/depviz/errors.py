"""Ошибки инструмента."""


class ConfigError(Exception):
    """Ошибки в конфигурационном файле.

    Хранит список сообщений, чтобы показать пользователю
    сразу все ошибки, а не только первую.
    """

    def __init__(self, messages):
        """Создать ошибку со списком сообщений.

        :param messages: список текстов ошибок.
        """
        super().__init__("\n".join(messages))
        self.messages = messages
