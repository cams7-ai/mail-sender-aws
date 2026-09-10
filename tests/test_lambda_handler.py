import json
from smtplib import SMTPException

from domain import ConfigurationError
from lambda_handler import handle_event


def test_handle_event_sends_email_successfully():
    sender = FakeEmailSender()

    response = handle_event(
        _event(
            {
                "to": "to@example.com",
                "subject": "Assunto",
                "body": "Mensagem",
                "message_type": "HTML",
            }
        ),
        sender,
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"message": "E-mail enviado com sucesso."}
    assert sender.messages[0].recipient == "to@example.com"
    assert sender.messages[0].subject == "Assunto"
    assert sender.messages[0].body == "Mensagem"
    assert sender.messages[0].message_type == "HTML"


def test_handle_event_rejects_invalid_payload():
    response = handle_event(_event({"to": "invalid", "subject": "", "body": ""}), FakeEmailSender())

    assert response["statusCode"] == 422
    assert json.loads(response["body"]) == {
        "error": {
            "code": "validation_error",
            "message": "Dados de entrada inválidos.",
        }
    }


def test_handle_event_returns_503_for_configuration_error():
    sender = FakeEmailSender(error=ConfigurationError("Configuração inválida."))

    response = handle_event(
        _event({"to": "to@example.com", "subject": "Assunto", "body": "Mensagem"}),
        sender,
    )

    assert response["statusCode"] == 503
    assert json.loads(response["body"]) == {
        "error": {
            "code": "configuration_error",
            "message": "Configuração inválida.",
        }
    }


def test_handle_event_returns_500_for_email_send_error():
    sender = FakeEmailSender(error=SMTPException("connection failed"))

    response = handle_event(
        _event({"to": "to@example.com", "subject": "Assunto", "body": "Mensagem"}),
        sender,
    )

    assert response["statusCode"] == 500
    assert json.loads(response["body"]) == {
        "error": {
            "code": "email_send_error",
            "message": "Falha ao enviar e-mail.",
        }
    }


def test_handle_event_returns_404_for_unknown_endpoint():
    response = handle_event(_event({}, method="GET", path="/api/v1/mail/unknown"), FakeEmailSender())

    assert response["statusCode"] == 404
    assert json.loads(response["body"]) == {
        "error": {
            "code": "not_found",
            "message": "Recurso não encontrado.",
        }
    }


def _event(body, method="POST", path="/api/v1/mail/send"):
    return {
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "body": json.dumps(body),
        "isBase64Encoded": False,
    }


class FakeEmailSender:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    def send(self, message):
        if self.error:
            raise self.error
        self.messages.append(message)
