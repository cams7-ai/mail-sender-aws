from domain import EmailMessageData
from domain import EmailSender


class SendEmailUseCase:
    def __init__(self, email_sender: EmailSender) -> None:
        self._email_sender = email_sender

    def execute(self, message: EmailMessageData) -> None:
        self._email_sender.send(message)
