from channels.messenger import MessengerAdapter
import pytest
from unittest.mock import AsyncMock, patch
import httpx


def test_messenger_adapter_name():
    assert MessengerAdapter().name == "messenger"


def test_messenger_parse_webhook_text_message():
    adapter = MessengerAdapter()
    payload = {
        "entry": [{
            "id": "PAGE_ID_123",
            "messaging": [{
                "sender": {"id": "PSID_USER_456"},
                "recipient": {"id": "PAGE_ID_123"},
                "message": {
                    "mid": "m_msg_abc",
                    "text": "hola desde Messenger",
                },
            }],
        }]
    }
    msgs = adapter.parse_webhook(payload)
    assert len(msgs) == 1
    assert msgs[0].channel == "messenger"
    assert msgs[0].external_user_id == "PSID_USER_456"
    assert msgs[0].text == "hola desde Messenger"
    assert msgs[0].metadata["page_id"] == "PAGE_ID_123"


@pytest.mark.anyio("asyncio")
async def test_messenger_send_message():
    adapter = MessengerAdapter()
    mock_creds = {"page_id": "P123", "page_access_token": "EAA_test"}
    mock_resp = httpx.Response(200, json={"message_id": "m_out_123"}, request=httpx.Request("POST", "https://graph.facebook.com"))

    with patch("channels.messenger._load_tenant_credentials", return_value=mock_creds), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await adapter.send_message("PSID_456", "Respuesta bot", tenant_id="t-123")
        assert res["message_id"] == "m_out_123"
        assert res["channel"] == "messenger"
