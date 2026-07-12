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