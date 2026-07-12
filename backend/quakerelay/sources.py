from dataclasses import dataclass

LOGICAL_SOURCES = {
    "cenc_eew": "中国地震台网预警",
    "sc_eew": "四川省地震预警",
    "fj_eew": "福建省地震预警",
    "cq_eew": "重庆市地震预警",
    "cenc_eqlist": "中国地震台网地震信息",
}


@dataclass(frozen=True)
class SourceDescriptor:
    channel: str
    logical_source: str
    display_name: str


def source_descriptor(key: str) -> SourceDescriptor:
    if key == "wolfx_ws":
        return SourceDescriptor("transport", "wolfx_ws", "Wolfx 实时连接")
    if key == "http:weather_rank":
        return SourceDescriptor("http", "weather_rank", "Wolfx 全国气象实况排行")
    if ":" in key:
        channel, logical_source = key.split(":", 1)
        display = LOGICAL_SOURCES.get(logical_source, logical_source)
        prefix = "实时" if channel == "ws" else "HTTP 补偿"
        return SourceDescriptor(channel, logical_source, f"{prefix} · {display}")
    return SourceDescriptor("unknown", key, key)
