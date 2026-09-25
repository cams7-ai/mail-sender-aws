import base64
import json
import logging
from typing import Any

from pydantic import ValidationError

from api.schemas import EmailRequest
from application import SendEmailUseCase
from domain import ConfigurationError
from domain import EmailMessageData
from domain import EmailSender
from infrastructure import SesEmailSender


SEND_MAIL_ROUTE = "POST /api/v1/mail/send"
logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle_event(event)


def handle_event(event: dict[str, Any], email_sender: EmailSender | None = None) -> dict[str, Any]:
    direct_invocation = "requestContext" not in event
    if not direct_invocation and not _is_send_mail_route(event):
        return _error_response(404, "not_found", "Recurso não encontrado.")

    try:
        payload = EmailRequest.model_validate(event if direct_invocation else _read_json_body(event))
        use_case = SendEmailUseCase(email_sender or SesEmailSender())
        use_case.execute(
            EmailMessageData(
                recipient=str(payload.to),
                subject=payload.subject,
                body=payload.body,
                message_type=payload.message_type,
            )
        )
    except ConfigurationError as exc:
        return _error_response(503, "configuration_error", str(exc))
    except (json.JSONDecodeError, ValidationError, ValueError):
        return _error_response(422, "validation_error", "Dados de entrada inválidos.")
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error", {}) if isinstance(response, dict) else {}
        code = error.get("Code", "unknown") if isinstance(error, dict) else "unknown"
        logger.error("Email send failed: type=%s code=%s", type(exc).__name__, code)
        return _error_response(500, "email_send_error", "Falha ao enviar e-mail.")

    return _json_response(200, {"message": "E-mail enviado com sucesso."})


def _is_send_mail_route(event: dict[str, Any]) -> bool:
    if event.get("routeKey") == SEND_MAIL_ROUTE:
        return True

    http = event.get("requestContext", {}).get("http", {})
    return http.get("method") == "POST" and event.get("rawPath") == "/api/v1/mail/send"


def _read_json_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if not body:
        raise ValueError("Request body is required.")

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def _error_response(status_code: int, code: str, message: str) -> dict[str, Any]:
    return _json_response(status_code, {"error": {"code": code, "message": message}})


def _json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }
