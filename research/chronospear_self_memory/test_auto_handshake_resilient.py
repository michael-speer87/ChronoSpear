from __future__ import annotations

import unittest
from unittest.mock import patch

import auto_handshake_resilient as resilient
from live_quest import ProviderResult


class ResilientHandshakeTests(unittest.TestCase):
    def test_429_retry_tracks_wait_separately(self) -> None:
        responses: list[object] = [
            RuntimeError(
                'Groq HTTP 429: rate limit reached. Please try again in 1.5s.'
            ),
            ProviderResult(
                'ANSWER: done\nEVIDENCE: none',
                {'prompt_tokens': 10, 'completion_tokens': 2},
            ),
        ]

        def fake_call_provider(messages: list[dict[str, str]]) -> ProviderResult:
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            assert isinstance(value, ProviderResult)
            return value

        provider = resilient.RateLimitAwareProvider(max_retries=2, quiet=True)
        with patch('auto_handshake_resilient.base.call_provider', side_effect=fake_call_provider):
            with patch('auto_handshake_resilient.sleep') as fake_sleep:
                result = provider([{'role': 'user', 'content': 'test'}])

        self.assertEqual(result.text, 'ANSWER: done\nEVIDENCE: none')
        self.assertEqual(provider.retry_count, 1)
        self.assertAlmostEqual(provider.total_wait_ms, 1750.0)
        self.assertEqual(provider.call_wait_ms, [1750.0])
        fake_sleep.assert_called_once_with(1.75)


if __name__ == '__main__':
    unittest.main()
