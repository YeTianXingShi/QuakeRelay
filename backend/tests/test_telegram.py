from quakerelay.notifications import telegram_message, telegram_request


def test_telegram_earthquake_message() -> None:
    payload = {
        "kind": "earthquake.initial",
        "delayed": False,
        "event": {
            "hypocenter": "四川宜宾市高县",
            "origin_time": "2026-07-12T07:41:08+00:00",
            "magnitude": 4.3,
            "depth_km": 10,
            "status": "preliminary",
            "sources": ["cenc_eew", "sc_eew"],
        },
        "impacts": [
            {
                "name": "家",
                "distance_km": 80.2,
                "estimated_intensity": 3.4,
                "intensity_level": 4,
                "estimation_status": "estimated",
            }
        ],
    }
    text = telegram_message(payload)
    assert "🌏 地震提醒" in text
    assert "2026-07-12 15:41:08（北京时间）" in text
    assert "预计烈度 3.4（4度）" in text
    assert "cenc_eew, sc_eew" in text


def test_telegram_request_supports_forum_topic() -> None:
    config = {
        "bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "chat_id": "-1001234567890",
        "message_thread_id": 42,
        "disable_notification": True,
    }
    url, body = telegram_request(config, {"kind": "system.test"})
    assert url.endswith("/sendMessage")
    assert config["bot_token"] in url
    assert body == {
        "chat_id": "-1001234567890",
        "text": "✅ QuakeRelay Telegram 测试成功",
        "disable_notification": True,
        "message_thread_id": 42,
    }


def test_telegram_system_status_message() -> None:
    text = telegram_message(
        {
            "kind": "system.source_down",
            "details": {"source": "wolfx_ws", "error": "timeout"},
        }
    )
    assert "数据源异常" in text
    assert "wolfx_ws" in text
    assert "timeout" in text
