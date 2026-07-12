from channels.base import ChannelAdapter, InboundMessage


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
        def refresh_token(self, credentials): return {"access_token": "y"}
        def send_message(self, recipient_id, text, **ctx): return {"message_id": "m1"}
        def parse_webhook(self, payload): return []

    assert isinstance(FakeAdapter(), ChannelAdapter)