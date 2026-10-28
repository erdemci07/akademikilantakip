import pytest

from akademik_ilan_takip.settings import ConfigurationError, Settings
from akademik_ilan_takip.telegram import send_message


@pytest.mark.asyncio
async def test_rejects_unauthorized_chat_before_network() -> None:
    settings = Settings("token", frozenset({1}), None, "x", "local", __import__("pathlib").Path("x"), None, "x", __import__("pathlib").Path("x"), 1, "test")
    with pytest.raises(ConfigurationError):
        await send_message(settings, 2, "test")
