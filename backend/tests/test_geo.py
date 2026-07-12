from quakerelay.geo import gcj02_to_wgs84, haversine_km, wgs84_to_gcj02


def test_haversine_known_distance() -> None:
    distance = haversine_km(39.9042, 116.4074, 31.2304, 121.4737)
    assert 1050 < distance < 1080


def test_gcj_round_trip() -> None:
    original = (39.9042, 116.4074)
    gcj = wgs84_to_gcj02(*original)
    restored = gcj02_to_wgs84(*gcj)
    assert gcj != original
    assert abs(restored[0] - original[0]) < 1e-6
    assert abs(restored[1] - original[1]) < 1e-6


def test_outside_china_is_unchanged() -> None:
    assert wgs84_to_gcj02(35.6762, 139.6503) == (35.6762, 139.6503)
