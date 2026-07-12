from channels.instagram import InstagramAdapter


def test_instagram_adapter_name():
    assert InstagramAdapter().name == "instagram"


def test_instagram_parse_webhook_text_message():
    adapter = InstagramAdapter()
    payload = {
        "entry": [{
            "id": "PAGE_ID_123",
            "messaging": [{
                "sender": {"id": "IGSID_USER_456"},
                "recipient": {"id": "IGSID_PAGE_789"},
                "message": {
                    "mid": "m_abc",
                    "text": "hola desde IG",
                },
            }],
        }]
    }
    msgs = adapter.parse_webhook(payload)
    assert len(msgs) == 1
    assert msgs[0].channel == "instagram"
    assert msgs[0].external_user_id == "IGSID_USER_456"
    assert msgs[0].text == "hola desde IG"