from datetime import datetime

import pytest

from core.schemas import BirthInfo
from computation import astrology
from computation.astrology import EphemerisError, compute_natal_chart, compute_transits


def _beijing_dst_birth() -> BirthInfo:
    return BirthInfo(
        gender="female",
        year=1991,
        month=8,
        day=15,
        hour=14,
        minute=30,
        location_name="北京",
        longitude=116.4074,
        latitude=39.9042,
        timezone_offset=9.0,
        use_true_solar_time=False,
    )


def test_natal_chart_uses_checked_swiss_ephemeris_files():
    chart = compute_natal_chart(_beijing_dst_birth())

    assert chart.metadata["ephemeris"] == "swisseph"
    assert chart.metadata["swisseph_version"]
    assert chart.planets["sun"]["longitude"] == pytest.approx(141.9139, abs=0.0001)
    assert chart.planets["moon"]["longitude"] == pytest.approx(208.8897, abs=0.0001)
    assert chart.planets["chiron"]["longitude"] == pytest.approx(122.8302, abs=0.0001)
    assert chart.angles["ASC"] == pytest.approx(237.0920, abs=0.0001)
    assert chart.house_system == "placidus"


def test_transits_use_checked_swiss_ephemeris_files():
    birth = _beijing_dst_birth()
    natal = compute_natal_chart(birth)
    transit = compute_transits(natal, datetime(2026, 5, 19, 12, 0), birth)

    assert transit.metadata["ephemeris"] == "swisseph"
    assert transit.metadata["swisseph_version"]
    assert "chiron" in transit.transit_planets


def test_missing_required_ephemeris_file_blocks_computation(monkeypatch):
    required = {
        **astrology.REQUIRED_EPHE_FILES,
        "missing_test_file.se1": {"size": 1, "sha256": "x"},
    }
    monkeypatch.setattr(astrology, "REQUIRED_EPHE_FILES", required)

    with pytest.raises(EphemerisError, match="数据文件缺失"):
        compute_natal_chart(_beijing_dst_birth())


def test_corrupt_required_ephemeris_file_blocks_computation(monkeypatch):
    required = {
        **astrology.REQUIRED_EPHE_FILES,
        "sepl_18.se1": {
            **astrology.REQUIRED_EPHE_FILES["sepl_18.se1"],
            "sha256": "0" * 64,
        },
    }
    monkeypatch.setattr(astrology, "REQUIRED_EPHE_FILES", required)

    with pytest.raises(EphemerisError, match="校验失败"):
        compute_natal_chart(_beijing_dst_birth())


def test_house_computation_failure_does_not_switch_house_system(monkeypatch):
    def fail_houses(*_args, **_kwargs):
        raise RuntimeError("houses unavailable")

    monkeypatch.setattr(astrology.swe, "houses_ex", fail_houses)

    with pytest.raises(EphemerisError, match="placidus 宫位"):
        compute_natal_chart(_beijing_dst_birth())
