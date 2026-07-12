from unittest.mock import patch

from channels.whatsapp import WhatsAppAdapter


def test_whatsapp_adapter_name():
    assert WhatsAppAdapter().name == "whatsapp"


def test_whatsapp_adapter_parse_webhook_yields_messages():
    adapter = WhatsAppAdapter()
    payload = {
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "56912345678",
                        "text": {"body": "hola"},
                        "id": "wamid.ABC",
                    }],
                    "metadata": {"phone_number_id": "PHONE_ID"},
                },
                "field": "messages",
            }],
        }]
    }
    msgs = adapter.parse_webhook(payload)
    assert len(msgs) == 1
    assert msgs[0].channel == "whatsapp"
    assert msgs[0].external_user_id == "56912345678"
    assert msgs[0].text == "hola"


def test_whatsapp_adapter_refresh_token_calls_fb_exchange():
    fake_settings = type("S", (), {
        "facebook_target_app_id": "X",
        "facebook_app_secret": "Y",
    })()
    with patch("channels.whatsapp.get_settings", return_value=fake_settings), \
         patch("httpx.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "access_token": "NEW_TOKEN",
            "expires_in": 5184000,
        }
        mock_get.return_value.raise_for_status = lambda: None
        adapter = WhatsAppAdapter()
        result = adapter.refresh_token({"access_token": "OLD_TOKEN"})
        assert result["access_token"] == "NEW_TOKEN"
        assert result["expires_in"] == 5184000
        called_url = mock_get.call_args.args[0]
        assert "/oauth/access_token" in called_url
        params = mock_get.call_args.kwargs["params"]
        assert params["grant_type"] == "fb_exchange_token"
        assert params["fb_exchange_token"] == "OLD_TOKEN"
        assert params["client_id"] == "X"
        assert params["client_secret"] == "Y"