"""Tests for Lanhu design sector mapping."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lanhu_mcp_server import _normalize_design_sectors


def test_normalize_sector_paths_and_multi_group_membership():
    sectors = [
        {
            "id": "root",
            "parent_id": "",
            "name": "首页",
            "order": 100,
            "images": ["img-1"],
        },
        {
            "id": "child",
            "parent_id": "root",
            "name": "弹窗",
            "order": 90,
            "images": ["img-1", "img-2"],
        },
        {
            "id": "other",
            "parent_id": "",
            "name": "活动",
            "order": 80,
            "images": ["img-1"],
        },
    ]

    normalized_sectors, image_sector_map = _normalize_design_sectors(sectors)

    assert [sector["path"] for sector in normalized_sectors] == [
        "首页",
        "首页/弹窗",
        "活动",
    ]
    assert [sector["name"] for sector in image_sector_map["img-1"]] == [
        "首页",
        "弹窗",
        "活动",
    ]
    assert [sector["path"] for sector in image_sector_map["img-2"]] == [
        "首页/弹窗",
    ]
    assert all(set(sector.keys()) == {"id", "name", "path"} for sector in image_sector_map["img-1"])


def test_normalize_sector_name_falls_back_to_id():
    sectors = [
        {
            "id": "unnamed-root",
            "parent_id": "",
            "name": None,
            "order": 10,
            "images": ["img-1"],
        },
        {
            "id": "unnamed-child",
            "parent_id": "unnamed-root",
            "name": "",
            "order": 5,
            "images": ["img-1"],
        },
    ]

    normalized_sectors, image_sector_map = _normalize_design_sectors(sectors)

    assert normalized_sectors[0]["name"] == "unnamed-root"
    assert normalized_sectors[0]["path"] == "unnamed-root"
    assert normalized_sectors[1]["name"] == "unnamed-child"
    assert normalized_sectors[1]["path"] == "unnamed-root/unnamed-child"
    assert image_sector_map["img-1"][0]["name"] == "unnamed-root"
    assert image_sector_map["img-1"][1]["name"] == "unnamed-child"


def test_normalize_deduplicates_sector_by_id_for_same_image():
    sectors = [
        {
            "id": "dup",
            "parent_id": "",
            "name": "分组A",
            "order": 1,
            "images": ["img-1", "img-1"],
        },
    ]

    _, image_sector_map = _normalize_design_sectors(sectors)

    assert len(image_sector_map["img-1"]) == 1
    assert image_sector_map["img-1"][0]["id"] == "dup"
