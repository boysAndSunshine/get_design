"""Tests for Sketch JSON design structure extraction."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lanhu_mcp_server import (
    build_design_structure_from_sketch,
    _parse_sketch_structure_tree,
)


def test_parse_nested_container_and_text():
    sketch_data = {
        "sliceScale": 2,
        "artboard": {
            "layers": [
                {
                    "id": "1",
                    "type": "group",
                    "name": "Header",
                    "frame": {"x": 0, "y": 0, "width": 375, "height": 88},
                    "layers": [
                        {
                            "id": "2",
                            "type": "textLayer",
                            "name": "Title",
                            "frame": {"x": 16, "y": 24, "width": 200, "height": 28},
                            "textContent": "Hello",
                            "textStyle": {
                                "fontSize": 20,
                                "fontWeight": 600,
                                "color": {"value": "rgba(0,0,0,1)"},
                            },
                        }
                    ],
                }
            ]
        },
    }

    nodes = _parse_sketch_structure_tree(sketch_data, is_figma=False)
    assert len(nodes) == 1
    assert nodes[0]["type"] == "container"
    assert nodes[0]["children"][0]["type"] == "text"
    assert nodes[0]["children"][0]["text"] == "Hello"
    assert nodes[0]["children"][0]["frame"]["width"] == 200


def test_parse_export_image_with_dds_image():
    sketch_data = {
        "meta": {"host": {"name": "sketch"}},
        "artboard": {
            "layers": [
                {
                    "id": "icon-1",
                    "type": "layer",
                    "name": "SearchIcon",
                    "frame": {"width": 24, "height": 24},
                    "ddsImage": {
                        "imageUrl": "https://example.com/icon.png",
                        "size": {"width": 24, "height": 24},
                    },
                }
            ]
        },
    }

    result = build_design_structure_from_sketch(sketch_data)
    assert result["status"] == "success"
    assert result["nodes"][0]["type"] == "icon"
    assert result["nodes"][0]["imageRef"] == "https://example.com/icon.png"


def test_parse_text_layer_with_text_info():
    sketch_data = {
        "board": {
            "layers": [
                {
                    "id": "t1",
                    "type": "textLayer",
                    "name": "Label",
                    "left": 10,
                    "top": 20,
                    "width": 100,
                    "height": 24,
                    "textInfo": {
                        "text": "Line1\rLine2",
                        "size": 14,
                        "color": {"red": 0, "green": 0, "blue": 0, "alpha": 1},
                    },
                }
            ]
        }
    }

    nodes = _parse_sketch_structure_tree(sketch_data, is_figma=False)
    assert nodes[0]["type"] == "text"
    assert "Line1" in nodes[0]["text"]
    assert nodes[0]["frame"]["x"] == 10
