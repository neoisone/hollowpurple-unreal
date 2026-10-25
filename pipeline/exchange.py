"""Prepare separate source/target scripts for a static mesh transfer, then verify its export."""

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path

from .setup import atomic_write, read_object

ASSETS = Path(__file__).with_name('assets.py').resolve()


def script(function, **kwargs):
    return ('import runpy\n'
            f'_transfer = runpy.run_path({str(ASSETS)!r})\n'
            f'print(_transfer[{function!r}](**{kwargs!r}))\n')


def prepare(direction, root, name, source):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
        raise ValueError('Use a simple asset name with letters, digits and underscores')
    if direction not in ('blender-to-unreal', 'unreal-to-blender'):
        raise ValueError('Unknown transfer direction')
    if not source or (direction == 'unreal-to-blender' and not source.startswith('/Game/')):
        raise ValueError('Provide the source Blender object name or Unreal /Game/ asset path')
    job = Path(root).resolve() / f'{name}_{uuid.uuid4().hex[:12]}'
    job.mkdir(parents=True, exist_ok=False)
    filepath = str(job / f'{name}.fbx')
    destination = f'/Game/Exchange/{job.name}'
    if direction == 'blender-to-unreal':
        source_code = script('blender_export', filepath=filepath, object_name=source)
        target_code = script('unreal_import', job_dir=str(job))
    else:
        source_code = script('unreal_export', filepath=filepath, asset_path=source)
        target_code = script('blender_import', job_dir=str(job))
    manifest = {'schema': 1, 'direction': direction, 'job_dir': str(job), 'file': filepath,
                'asset_name': name, 'source': source, 'unreal_destination': destination}
    (job / 'source.py').write_text(source_code, encoding='utf-8')
    (job / 'target.py').write_text(target_code, encoding='utf-8')
    atomic_write(job / 'job.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return manifest


def verify(job_dir):
    job = Path(job_dir).resolve()
    manifest = read_object(job / 'job.json')
    if manifest.get('schema') != 1:
        raise ValueError('Unsupported transfer manifest schema')
    name = manifest['asset_name']
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
        raise ValueError('Invalid asset name in transfer manifest')
    path = Path(manifest['file']).resolve()
    if path.parent != job or path.name != f'{name}.fbx':
        raise ValueError('Export file must be inside this transfer directory')
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    if not size:
        raise ValueError('Export is empty')
    sha = digest.hexdigest()
    if manifest.get('sha256') and manifest['sha256'] != sha:
        raise ValueError('Export changed after verification; create a new transfer')
    manifest.update({'sha256': sha, 'bytes': size})
    atomic_write(job / 'job.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('--direction', required=True, choices=['blender-to-unreal', 'unreal-to-blender'])
    prepare_parser.add_argument('--exchange', type=Path, required=True)
    prepare_parser.add_argument('--name', required=True)
    prepare_parser.add_argument('--source', required=True)
    verify_parser = sub.add_parser('verify')
    verify_parser.add_argument('job_dir', type=Path)
    args = parser.parse_args()
    result = (prepare(args.direction, args.exchange, args.name, args.source)
              if args.command == 'prepare' else verify(args.job_dir))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
