from datetime import datetime

from api.routes import CreateOrUpdateSession, _profile_to_birthinfo
import pytest

from core.geo import GeoResolutionError, infer_timezone_offset, resolve_geo


def test_resolve_geo_handles_alias_and_district_names():
    coord, kind, matched = resolve_geo("上海浦东新区")
    assert kind == "admin_adcode"
    assert matched == "浦东新区"
    assert coord == (121.55045461, 31.22734829)

    coord, kind, matched = resolve_geo("北京海淀")
    assert kind == "alias"
    assert matched == "海淀"
    assert coord == (116.298, 39.9593)


def test_resolve_geo_handles_continuous_admin_text():
    coord, kind, matched = resolve_geo("江西省赣州市瑞金")
    assert kind == "admin_adcode"
    assert matched == "瑞金市"
    assert coord == (116.03342066, 25.89166627)

    coord, kind, matched = resolve_geo("广东省深圳市南山区")
    assert kind == "admin_adcode"
    assert matched == "南山区"
    assert coord == (113.93653917, 22.5385002)


def test_resolve_geo_handles_overseas_aliases():
    with pytest.raises(GeoResolutionError, match="暂不支持海外"):
        resolve_geo("美国加州伯克利")

    with pytest.raises(GeoResolutionError, match="暂不支持海外"):
        resolve_geo("Berkeley, CA")


def test_resolve_geo_does_not_fallback_to_beijing():
    with pytest.raises(GeoResolutionError):
        resolve_geo("某个完全不存在的小乡村")


def test_resolve_geo_rejects_province_level_place():
    with pytest.raises(GeoResolutionError, match="只到省级"):
        resolve_geo("江苏")


def test_infer_timezone_offset_from_matched_place():
    from core.geo import TimezoneResolutionError

    with pytest.raises(TimezoneResolutionError, match="暂不支持海外"):
        infer_timezone_offset(
            "美国加州伯克利", "伯克利", -122.2727, 37.8715, datetime(1991, 8, 15, 14, 30)
        )


def test_infer_timezone_offset_keeps_china_on_beijing_time():
    offset, confidence, source = infer_timezone_offset("新疆喀什", "喀什", 75.9554, 39.4677)
    assert offset == 8.0
    assert confidence == "exact"
    assert source == "Asia/Shanghai"


def test_infer_timezone_offset_respects_china_historical_dst():
    offset, confidence, source = infer_timezone_offset(
        "北京", "北京", 116.4074, 39.9042, datetime(1988, 6, 1, 12, 0)
    )
    assert offset == 9.0
    assert confidence == "exact"
    assert source == "Asia/Shanghai"


def test_profile_to_birthinfo_rejects_overseas_place():
    req = CreateOrUpdateSession(
        name="A",
        gender="female",
        date="1991-08-15",
        time="14:30",
        place="美国加州伯克利",
        timezone_offset=None,
    )
    with pytest.raises(ValueError, match="暂不支持海外"):
        _profile_to_birthinfo(req.model_dump())


def test_profile_to_birthinfo_rejects_missing_or_unresolved_place():
    req = CreateOrUpdateSession(
        name="A",
        gender="female",
        date="1991-08-15",
        time="14:30",
        place="某个完全不存在的小乡村",
    )
    with pytest.raises(ValueError, match="无法识别出生地"):
        _profile_to_birthinfo(req.model_dump())


def test_profile_to_birthinfo_rejects_province_level_place():
    req = CreateOrUpdateSession(
        name="A",
        gender="female",
        date="1991-08-15",
        time="14:30",
        place="江苏",
    )
    with pytest.raises(ValueError, match="只到省级"):
        _profile_to_birthinfo(req.model_dump())


def test_profile_to_birthinfo_rejects_unknown_birth_time():
    req = CreateOrUpdateSession(
        name="A",
        gender="female",
        date="1991-08-15",
        time=None,
        unknownTime=True,
        place="杭州",
    )
    with pytest.raises(ValueError, match="未知时辰无法生成完整盘面"):
        _profile_to_birthinfo(req.model_dump())
