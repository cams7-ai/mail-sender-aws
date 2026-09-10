import os

import boto3

from domain import ConfigurationError
from domain import EmailMessageData


class SesEmailSender:
    def __init__(self, ses_client=None, sender: str | None = None) -> None:
        self._client = ses_client or boto3.client("sesv2")
        self._sender = sender or self._load_sender()

    def send(self, message: EmailMessageData) -> None:
        body_key = "Html" if (message.message_type or "").upper() == "HTML" else "Text"
        self._client.send_email(
            FromEmailAddress=self._sender,
            Destination={"ToAddresses": [message.recipient]},
            Content={
                "Simple": {
                    "Subject": {"Data": message.subject},
                    "Body": {body_key: {"Data": message.body}},
                }
            },
        )

    def _load_sender(self) -> str:
        sender = os.getenv("SES_FROM")
        if not sender:
            raise ConfigurationError("Variável SES_FROM não configurada.")
        return sender
