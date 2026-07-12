import pytest
from channels.base import ChannelAdapter, InboundMessage
from channels.registry import get_adapter, register_adapter, known_channels


def test_inbound_message_dataclass():
    msg = InboundMessage(
        channel="instagram",
        external_user_id="IGSID_123",
        text="hola",
        raw={"entry": []},
    )
    assert msg.channel == "instagram"
    assert msg.external_user_id == "IGSID_123"
    assert msg.text == "hola"


def test_adapter_protocol_is_runtime_checkable():
    class FakeAdapter:
        name = "fake"

        def exchange_oauth(self, code, **ctx): return {"access_token": "x"}
        def refresh_token(self, credentials, **ctx): return {"access_token": "y"}
        async def send_message(self, recipient_id, text, **ctx): return {"message_id": "m1"}
        def parse_webhook(self, payload): return []

    assert isinstance(FakeAdapter(), ChannelAdapter)


def test_get_adapter_raises_keyerror():
    with pytest.raises(KeyError):
        get_adapter("does-not-exist")


def test_register_adapter_raises_on_collision():
    class A:
        name = "dup"
        def exchange_oauth(self, code, **c): return {}
        def refresh_token(self, credentials, **c): return {}
        def send_message(self, r, t, **c): return {}
        def parse_webhook(self, p): return []
    register_adapter(A())
    with pytest.raises(ValueError, match="already registered"):
        register_adapter(A())


def test_known_channels_lists_registered():
    class B:
        name = "channel_b_test"
        def exchange_oauth(self, code, **c): return {}
        def refresh_token(self, credentials, **c): return {}
        def send_message(self, r, t, **c): return {}
        def parse_webhook(self, p): return []
    register_adapter(B())
    assert "channel_b_test" in known_channels()


def test_inbound_message_independent_defaults():
    """Two instances must not share the same raw/metadata dict."""
    a = InboundMessage(channel="x", external_user_id="1", text="t")
    b = InboundMessage(channel="x", external_user_id="1", text="t")
    a.raw["k"] = 1
    a.metadata["k"] = 1
    assert b.raw == {}
    assert b.metadata == {}