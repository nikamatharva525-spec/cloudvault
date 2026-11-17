import os
import unittest
from unittest.mock import patch

from app.security import (
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    is_valid_credentials,
    is_valid_password,
    is_valid_session_token,
    _hash_password,
    validate_auth_configuration,
)


class SessionSecurityTests(unittest.TestCase):
    def test_signed_session_is_valid_until_expiry(self):
        token = create_session_token("session-secret-for-tests-that-is-long-enough", now=100)

        self.assertTrue(
            is_valid_session_token(
                token,
                "session-secret-for-tests-that-is-long-enough",
                now=100 + SESSION_MAX_AGE_SECONDS - 1,
            )
        )
        self.assertFalse(
            is_valid_session_token(
                token,
                "session-secret-for-tests-that-is-long-enough",
                now=100 + SESSION_MAX_AGE_SECONDS,
            )
        )

    def test_tampered_or_malformed_session_is_rejected(self):
        token = create_session_token("session-secret-for-tests-that-is-long-enough", now=100)
        payload, signature = token.split(".", 1)

        self.assertFalse(
            is_valid_session_token(
                f"{payload[:-1]}x.{signature}",
                "session-secret-for-tests-that-is-long-enough",
                now=101,
            )
        )
        self.assertFalse(is_valid_session_token("not-a-session", "secret", now=101))

    def test_auth_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CLOUDVAULT_ACCESS_PASSWORD"):
                validate_auth_configuration()

    def test_password_comparison_uses_configured_value(self):
        with patch.dict(
            os.environ,
            {
                "CLOUDVAULT_ACCESS_PASSWORD": "a-test-password",
                "CLOUDVAULT_SESSION_SECRET": "session-secret-for-tests-that-is-long-enough",
            },
            clear=True,
        ):
            self.assertTrue(is_valid_password("a-test-password"))
            self.assertFalse(is_valid_password("incorrect-password"))

    def test_registered_credentials_override_configured_credentials_locally(self):
        with patch.dict(
            os.environ,
            {
                "CLOUDVAULT_ACCESS_EMAIL": "owner@example.com",
                "CLOUDVAULT_ACCESS_PASSWORD": "configured-password",
                "CLOUDVAULT_SESSION_SECRET": "session-secret-for-tests-that-is-long-enough",
            },
            clear=True,
        ), patch("app.security._read_registered_user", return_value={
            "email": "owner@example.com",
            "salt": "dGVzdC1zYWx0",
            "password_hash": _hash_password("old-password", "dGVzdC1zYWx0"),
        }):
            self.assertFalse(is_valid_credentials("owner@example.com", "configured-password"))
            self.assertTrue(is_valid_credentials("owner@example.com", "old-password"))


if __name__ == "__main__":
    unittest.main()
