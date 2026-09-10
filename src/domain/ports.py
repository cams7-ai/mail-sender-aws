from typing import Protocol

from domain import EmailMessageData


class EmailSender(Protocol):
    def send(self, message: EmailMessageData) -> None:
        pass
