from quakerelay.intensity import ChinaRegionalIntensityModel


def test_nearby_moderate_earthquake_triggers() -> None:
    result = ChinaRegionalIntensityModel().estimate(
        magnitude=5.0,
        depth_km=10,
        event_latitude=30.0,
        event_longitude=110.0,
        location_latitude=30.05,
        location_longitude=110.05,
    )
    assert result.triggered
    assert result.estimated_intensity is not None
    assert result.estimated_intensity >= 2
    assert result.confidence == "high"
    assert result.status == "estimated"


def test_far_small_earthquake_does_not_trigger() -> None:
    result = ChinaRegionalIntensityModel().estimate(
        magnitude=2.0,
        depth_km=10,
        event_latitude=20.0,
        event_longitude=110.0,
        location_latitude=27.5,
        location_longitude=110.0,
    )
    assert not result.triggered
    assert result.status == "estimated"


def test_missing_magnitude_fails_open_within_300km() -> None:
    result = ChinaRegionalIntensityModel().estimate(
        magnitude=None,
        depth_km=None,
        event_latitude=30.0,
        event_longitude=110.0,
        location_latitude=31.0,
        location_longitude=110.0,
    )
    assert result.triggered
    assert result.estimated_intensity is None
    assert result.confidence == "low"
    assert result.status == "insufficient_data"


def test_out_of_range_has_explicit_status() -> None:
    result = ChinaRegionalIntensityModel().estimate(
        magnitude=7.0,
        depth_km=10,
        event_latitude=20.0,
        event_longitude=110.0,
        location_latitude=40.0,
        location_longitude=110.0,
    )
    assert result.status == "out_of_range"
    assert result.estimated_intensity is None
    assert not result.triggered


def test_transition_band_uses_conservative_model() -> None:
    model = ChinaRegionalIntensityModel()
    result = model.estimate(
        magnitude=4.5,
        depth_km=15,
        event_latitude=30,
        event_longitude=105,
        location_latitude=30.5,
        location_longitude=105,
    )
    assert result.estimated_intensity is not None
    assert result.model_version == model.version
