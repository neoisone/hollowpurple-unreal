"""Run these functions inside Blender or Unreal's editor Python, never in external Python."""

import hashlib
import json
from pathlib import Path


def export_path(filepath):
    path = Path(filepath).resolve()
    if path.suffix.lower() != '.fbx' or not path.parent.is_dir():
        raise ValueError('Use an .fbx file in an existing transfer directory')
    if path.exists():
        raise FileExistsError(path)
    return path


def verified_job(job_dir, direction):
    job = Path(job_dir).resolve()
    manifest = json.loads((job / 'job.json').read_text(encoding='utf-8'))
    path = Path(manifest['file']).resolve()
    if (manifest.get('schema') != 1 or manifest.get('direction') != direction or
            path.parent != job or path.suffix.lower() != '.fbx' or not manifest.get('sha256')):
        raise ValueError('Run pipeline.exchange verify on the correct transfer before importing')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != manifest['sha256']:
        raise ValueError('Export changed after verification; create a new transfer')
    return manifest, path


def blender_export(filepath, object_name):
    import bpy

    path = export_path(filepath)
    obj = bpy.context.view_layer.objects.get(object_name)
    if obj is None or obj.type != 'MESH':
        raise ValueError('Select a named mesh object in the current view layer')
    if bpy.context.mode != 'OBJECT' or any(m.type == 'ARMATURE' for m in obj.modifiers):
        raise ValueError('This helper exports static meshes in Object Mode; use a separate skeletal workflow')
    if abs(bpy.context.scene.unit_settings.scale_length - 1.0) > 1e-6:
        raise ValueError('Static transfer expects Blender unit scale 1.0 (meters); normalize a copy first')
    selected, active = list(bpy.context.selected_objects), bpy.context.view_layer.objects.active
    try:
        for item in selected:
            item.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        result = bpy.ops.export_scene.fbx(
            filepath=str(path), use_selection=True, object_types={'MESH'},
            axis_forward='-Y', axis_up='Z', apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_UNITS', use_mesh_modifiers=True,
            mesh_smooth_type='FACE', bake_anim=False, path_mode='AUTO')
        if result != {'FINISHED'} or not path.is_file() or not path.stat().st_size:
            raise RuntimeError('Blender FBX export did not finish')
    finally:
        obj.select_set(False)
        for item in selected:
            item.select_set(True)
        bpy.context.view_layer.objects.active = active
    return {'file': str(path), 'bytes': path.stat().st_size, 'object': object_name}


def blender_import(job_dir):
    import bpy

    manifest, path = verified_job(job_dir, 'unreal-to-blender')
    if bpy.context.mode != 'OBJECT':
        raise ValueError('Switch to Object Mode before importing')
    collection_name = 'Exchange_' + Path(job_dir).name
    if bpy.data.collections.get(collection_name) is not None:
        raise FileExistsError('This transfer was already imported; create a new transfer')
    before = set(bpy.data.objects)
    result = bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False)
    if result != {'FINISHED'}:
        raise RuntimeError('Blender FBX import did not finish')
    imported = set(bpy.data.objects) - before
    if not imported:
        raise RuntimeError('FBX import created no objects')
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)
    for obj in imported:
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)
    return {'objects': sorted(obj.name for obj in imported), 'collection': collection.name,
            'source_sha256': manifest['sha256']}


def unreal_export(filepath, asset_path):
    import unreal

    path = export_path(filepath)
    asset = unreal.load_asset(asset_path)
    if not isinstance(asset, unreal.StaticMesh):
        raise ValueError('This helper exports one StaticMesh asset; use separate animation/scene workflows')
    task = unreal.AssetExportTask()
    task.set_editor_property('object', asset)
    task.set_editor_property('filename', str(path))
    task.set_editor_property('automated', True)
    task.set_editor_property('prompt', False)
    task.set_editor_property('replace_identical', False)
    task.set_editor_property('exporter', unreal.StaticMeshExporterFBX())
    task.set_editor_property('options', unreal.FbxExportOption())
    if not unreal.Exporter.run_asset_export_task(task) or not path.is_file() or not path.stat().st_size:
        raise RuntimeError(f'Unreal FBX export failed: {list(task.errors)}')
    return {'file': str(path), 'bytes': path.stat().st_size, 'asset': asset_path}


def unreal_import(job_dir):
    import unreal

    manifest, path = verified_job(job_dir, 'blender-to-unreal')
    destination = manifest['unreal_destination']
    if not destination.startswith('/Game/Exchange/') or '..' in destination:
        raise ValueError('Import destination must be a new /Game/Exchange/ folder')
    if unreal.EditorAssetLibrary.does_directory_exist(destination):
        raise FileExistsError('Destination already exists; create a new transfer')
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(path), 'destination_path': destination,
                       'destination_name': manifest['asset_name'], 'automated': True,
                       'replace_existing': False, 'save': False}.items():
        task.set_editor_property(key, value)
    # Use the project's active importer; do not toggle global Interchange feature flags.
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = list(task.get_editor_property('imported_object_paths'))
    if not paths or not any(isinstance(unreal.load_asset(p), unreal.StaticMesh) for p in paths):
        raise RuntimeError('Import returned no StaticMesh. Inspect Unreal Output Log and active importer settings.')
    return {'assets': paths, 'destination': destination, 'saved': False,
            'source_sha256': manifest['sha256']}
