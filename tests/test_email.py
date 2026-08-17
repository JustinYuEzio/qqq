import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


RUN_PATH = Path(__file__).resolve().parents[1] / "src" / "run.py"
SPEC = importlib.util.spec_from_file_location("qqq_run_email_tests", RUN_PATH)
run = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = run
SPEC.loader.exec_module(run)


class FakeSmtp:
    sent_message = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def login(self, username, password):
        pass

    def send_message(self, message):
        type(self).sent_message = message


class EmailTests(unittest.TestCase):
    def test_deliver_email_uses_selected_recipient(self):
        settings = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "sender@example.com",
            "SMTP_PASSWORD": "secret",
            "ALERT_TO_EMAIL": "selected@example.com",
        }
        FakeSmtp.sent_message = None
        with (
            patch.dict(os.environ, settings, clear=True),
            patch.object(run.ssl, "create_default_context", return_value=object()),
            patch.object(run.smtplib, "SMTP_SSL", FakeSmtp),
        ):
            run.deliver_email("Subject", "Body")

        self.assertIsNotNone(FakeSmtp.sent_message)
        self.assertEqual(FakeSmtp.sent_message["To"], "selected@example.com")

    def test_deliver_email_requires_recipient(self):
        settings = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "sender@example.com",
            "SMTP_PASSWORD": "secret",
        }
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ALERT_TO_EMAIL"):
                run.deliver_email("Subject", "Body")


if __name__ == "__main__":
    unittest.main()
