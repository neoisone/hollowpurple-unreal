"""Run only in a new --background --factory-startup Blender process."""

import argparse
import json
import runpy
import sys
from pathlib import Path

import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.output.mkdir(parents=True, exist_ok=False)
helpers = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'pipeline/assets.py'))
filepath = args.output / 'SM_Cube.fbx'
result = helpers['blender_export'](str(filepath), 'Cube')
assert result['bytes'] > 0
manifest = {'schema': 1, 'direction': 'unreal-to-blender', 'asset_name': 'SM_Cube',
            'file': str(filepath), 'job_dir': str(args.output)}
(args.output / 'job.json').write_text(json.dumps(manifest))
# Verify import through the public CLI before the target consumes the file.
import hashlib
manifest['sha256'] = hashlib.sha256(filepath.read_bytes()).hexdigest()
(args.output / 'job.json').write_text(json.dumps(manifest))
report = helpers['blender_import'](str(args.output))
assert len(report['objects']) == 1, report
obj = bpy.data.objects[report['objects'][0]]
assert all(abs(float(value) - 2.0) < 0.002 for value in obj.dimensions), list(obj.dimensions)
assert bpy.data.objects.get('Cube') is not None
try:
    helpers['blender_export'](str(filepath), 'Cube')
except FileExistsError:
    pass
else:
    raise AssertionError('Existing export was overwritten')
print('BLENDER_EXCHANGE_REPORT=' + json.dumps({'export': result, 'import': report,
                                              'dimensions_m': list(obj.dimensions)}))
