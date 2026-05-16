#!/usr/bin/env python3
"""CLI: export AI-friendly design blueprint JSON from Lanhu."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env', override=False)
except ImportError:
    pass

from lanhu_mcp_server import (
    LanhuExtractor,
    _get_designs_internal,
    _resolve_target_design,
    build_ai_design_blueprint,
    _save_design_blueprint_file,
)


async def run(url: str, image_id: str | None, design_name: str | None) -> int:
    extractor = LanhuExtractor()
    try:
        target_image_id, target_design, third = await _resolve_target_design(
            extractor, url, image_id, design_name
        )
        if not target_image_id:
            print(json.dumps(third, ensure_ascii=False, indent=2))
            return 1

        params = third
        designs_data = await _get_designs_internal(extractor, url)
        if not target_design and designs_data.get('status') == 'success':
            target_design = next(
                (d for d in designs_data['designs'] if d['id'] == target_image_id),
                None,
            )

        sketch = await extractor.get_sketch_json(
            target_image_id, params['team_id'], params['project_id']
        )
        dds_ok = True
        try:
            await extractor.get_design_schema_json(
                target_image_id, params['team_id'], params['project_id']
            )
        except Exception:
            dds_ok = False

        blueprint = build_ai_design_blueprint(
            sketch,
            design=target_design,
            project_name=designs_data.get('project_name'),
            project_id=params['project_id'],
            dds_schema_available=dds_ok,
        )
        blueprint['files'] = _save_design_blueprint_file(
            params['project_id'], target_image_id, blueprint
        )
        print(json.dumps({
            'status': 'success',
            'designName': (target_design or {}).get('name'),
            'files': blueprint['files'],
            'summary': blueprint['summary'],
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False, indent=2))
        return 1
    finally:
        await extractor.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='Export Lanhu design blueprint for AI')
    parser.add_argument('--url', required=True, help='Lanhu design URL (with tid, pid, optional image_id)')
    parser.add_argument('--image-id', default=None, help='Design image ID')
    parser.add_argument('--design-name', default=None, help='Design name from lanhu_get_designs')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.url, args.image_id, args.design_name)))


if __name__ == '__main__':
    main()
