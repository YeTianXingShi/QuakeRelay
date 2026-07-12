from quakerelay.collector import QUERY_COMMANDS
from quakerelay.sources import LOGICAL_SOURCES, source_descriptor


def test_source_health_descriptors() -> None:
    transport = source_descriptor("wolfx_ws")
    assert transport.channel == "transport"
    assert transport.display_name == "Wolfx 实时连接"

    realtime = source_descriptor("ws:cenc_eew")
    assert realtime.channel == "ws"
    assert realtime.logical_source == "cenc_eew"
    assert realtime.display_name == "实时 · 中国地震台网预警"

    fallback = source_descriptor("http:sc_eew")
    assert fallback.channel == "http"
    assert fallback.display_name == "HTTP 补偿 · 四川省地震预警"


def test_every_logical_source_has_an_initial_websocket_query() -> None:
    expected = {
        "sc_eew": "query_sceew",
        "fj_eew": "query_fjeew",
        "cq_eew": "query_cqeew",
        "cenc_eew": "query_cenceew",
        "cenc_eqlist": "query_cenceqlist",
    }
    assert set(expected) == set(LOGICAL_SOURCES)
    assert QUERY_COMMANDS == expected
