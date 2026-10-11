from unittest.mock import MagicMock, patch

from app import email_service


def test_send_email_returns_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_HOST", None)
    monkeypatch.setattr(email_service, "SMTP_USER", None)
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", None)
    assert email_service.send_email("someone@test.com", "제목", "내용") is False


def test_send_email_returns_false_when_recipient_missing(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_HOST", "smtp.test.com")
    monkeypatch.setattr(email_service, "SMTP_USER", "user@test.com")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "secret")
    assert email_service.send_email("", "제목", "내용") is False


def test_send_email_succeeds_when_configured(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_HOST", "smtp.test.com")
    monkeypatch.setattr(email_service, "SMTP_PORT", 587)
    monkeypatch.setattr(email_service, "SMTP_USER", "user@test.com")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(email_service, "SMTP_FROM", "user@test.com")

    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_server
        result = email_service.send_email("someone@test.com", "제목", "내용")

    assert result is True
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user@test.com", "secret")
    mock_server.sendmail.assert_called_once()


def test_send_email_returns_false_on_smtp_error(monkeypatch):
    monkeypatch.setattr(email_service, "SMTP_HOST", "smtp.test.com")
    monkeypatch.setattr(email_service, "SMTP_USER", "user@test.com")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "secret")

    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        result = email_service.send_email("someone@test.com", "제목", "내용")

    assert result is False
