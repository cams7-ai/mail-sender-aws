import pytest

from domain import ConfigurationError
from domain import EmailMessageData
from infrastructure import SesEmailSender


def test_ses_email_sender_sends_text_email():
    client = FakeSesClient()
    sender = SesEmailSender(ses_client=client, sender="from@example.com")

    sender.send(EmailMessageData(recipient="to@example.com", subject="Assunto", body="Mensagem"))

    assert client.calls == [
        {
            "FromEmailAddress": "from@example.com",
            "Destination": {"ToAddresses": ["to@example.com"]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": "Assunto"},
                    "Body": {"Text": {"Data": "Mensagem"}},
                }
            },
        }
    ]


def test_ses_email_sender_sends_html_email():
    client = FakeSesClient()
    sender = SesEmailSender(ses_client=client, sender="from@example.com")

    sender.send(EmailMessageData(recipient="to@example.com", subject="Assunto", body="<b>Mensagem</b>", message_type="HTML"))

    assert client.calls[0]["Content"]["Simple"]["Body"] == {"Html": {"Data": "<b>Mensagem</b>"}}


def test_ses_email_sender_requires_sender(monkeypatch):
    monkeypatch.delenv("SES_FROM", raising=False)

    with pytest.raises(ConfigurationError, match="SES_FROM"):
        SesEmailSender(ses_client=FakeSesClient())


class FakeSesClient:
    def __init__(self):
        self.calls = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
