import io
import json
import logging

from app.core.logging import JsonFormatter, request_id_var


def _logger_with_stream() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.json_logger")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_json_log_contains_request_id_and_extras() -> None:
    logger, stream = _logger_with_stream()
    token = request_id_var.set("req-12345678")
    try:
        logger.info("hello", extra={"path": "/x"})
    finally:
        request_id_var.reset(token)
    entry = json.loads(stream.getvalue())
    assert entry["message"] == "hello"
    assert entry["level"] == "INFO"
    assert entry["request_id"] == "req-12345678"
    assert entry["path"] == "/x"


def test_sensitive_extras_are_redacted() -> None:
    logger, stream = _logger_with_stream()
    logger.info("login", extra={"password": "hunter2", "refresh_token": "abc", "user": "amina"})
    entry = json.loads(stream.getvalue())
    assert entry["password"] == "[REDACTED]"
    assert entry["refresh_token"] == "[REDACTED]"
    assert entry["user"] == "amina"
    assert "hunter2" not in stream.getvalue()
