"""Tests for AI design blueprint export."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lanhu_mcp_server import (
    build_ai_design_blueprint,
    _clean_blueprint_node,
    _extract_all_text_contents_from_sketch,
    _flatten_blueprint_nodes,
)


def test_build_blueprint_extracts_plain_text():
    sketch = {
        "sliceScale": 2,
        "meta": {"host": {"name": "figma"}},
        "artboard": {
            "layers": [
                {
                    "id": "1",
                    "type": "text",
                    "name": "Title",
                    "frame": {"x": 10, "y": 20, "width": 100, "height": 24},
                    "style": {"content": "Hello World"},
                }
            ]
        },
    }
    blueprint = build_ai_design_blueprint(
        sketch,
        design={"id": "d1", "name": "Test", "width": 375, "height": 812},
        project_name="Demo",
        project_id="p1",
        dds_schema_available=False,
    )
    assert blueprint["status"] == "success"
    assert "Hello World" in blueprint["summary"]["allTexts"]
    assert blueprint["textBlocks"][0]["text"] == "Hello World"
    assert blueprint["wireframeAscii"]
    title_node = blueprint["layerTree"][0]
    assert title_node.get("text") == "Hello World" or (
        title_node.get("children") and title_node["children"][0]["text"] == "Hello World"
    )


def test_clean_blueprint_node_strips_style_blob():
    raw = {
        "type": "text",
        "name": "Label",
        "text": "{'style': {'content': 'OK'}}",
        "frame": {"x": 0, "y": 0, "width": 10, "height": 10},
    }
    cleaned = _clean_blueprint_node(raw)
    assert cleaned.get("text") == "OK"


def test_flatten_blueprint_nodes_paths():
    tree = [{
        "type": "container",
        "name": "Root",
        "children": [{"type": "text", "name": "Child", "text": "A", "frame": {"x": 1, "y": 2, "width": 3, "height": 4}}],
    }]
    flat = _flatten_blueprint_nodes(tree)
    assert len(flat) == 2
    assert flat[1]["path"] == "Root/Child"
