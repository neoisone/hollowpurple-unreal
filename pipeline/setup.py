"""Inspect or apply a native Unreal 5.8 MCP setup; inspection is the default."""

import argparse
import codecs
import copy
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

PLUGINS = ('ModelContextProtocol', 'AllToolsets', 'PythonScriptPlugin', 'EditorScriptingUtilities')
SECTION = '/Script/ModelContextProtocolEngine.ModelContextProtocolSettings'
SERVER = 'unreal-mcp'
ROOT = Path(__file__).resolve().parents[1]


def read_object(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected a JSON object: {path}')
    return value


def ini_format(data):
    for bom, encoding in ((codecs.BOM_UTF16_LE, 'utf-16-le'),
                          (codecs.BOM_UTF16_BE, 'utf-16-be'), (codecs.BOM_UTF8, 'utf-8')):
        if data.startswith(bom):
            return bom, encoding
    return b'', 'utf-8'


def read_ini(path):
    data = path.read_bytes()
    bom, encoding = ini_format(data)
    return data[len(bom):].decode(encoding)


def client_entry(client, port, uv=None):
    if not 1 <= port <= 65535:
        raise ValueError('Port must be between 1 and 65535')
    url = f'http://127.0.0.1:{port}/mcp'
    if client == 'code':
        return {'type': 'http', 'url': url}
    if client != 'desktop' or uv is None:
        raise ValueError('Desktop setup requires the actual uv executable path')
    return {'command': str(uv), 'args': [
        'run', '--frozen', '--project', str(ROOT), '--python', '3.11',
        'mcp-proxy', '--log-level', 'ERROR', '--transport', 'streamablehttp', url],
        'env': {'UV_PYTHON_PREFERENCE': 'only-managed'}}


def set_ini_values(text, section, values):
    """Change only named keys in a section; preserve comments and other sections."""
    output = []
    inside = False
    inserted = False
    keys = {key.casefold() for key in values}
    for line in text.splitlines():
        match = re.match(r'^\s*\[([^]]+)\]\s*$', line)
        if match:
            inside = match[1].casefold() == section.casefold()
            output.append(line)
            if inside and not inserted:
                output.extend(f'{key}={value}' for key, value in values.items())
                inserted = True
            continue
        if inside and '=' in line and line.split('=', 1)[0].strip().casefold() in keys:
            continue
        output.append(line)
    if not inserted:
        output.extend(['', f'[{section}]', *(f'{key}={value}' for key, value in values.items())])
    return '\n'.join(output).lstrip('\n') + '\n'


def check_binding(project):
    """Refuse an explicit project override that exposes the shared HTTP listener."""
    for folder in (project.parent / 'Config', project.parent / 'Saved/Config'):
        for path in folder.rglob('*.ini'):
            inside = False
            for line in read_ini(path).splitlines():
                if line.strip().startswith('['):
                    inside = line.strip().casefold() == '[httpserver.listeners]'
                if inside and '=' in line:
                    key, value = line.split('=', 1)
                    if key.strip().casefold() == 'defaultbindaddress' and value.strip().strip('"') not in (
                            '127.0.0.1', 'localhost', '::1'):
                        raise ValueError(f'MCP must use loopback; inspect DefaultBindAddress in {path}')


@dataclass
class Change:
    path: Path
    before: bytes | None
    after: bytes


def change(path, content):
    before = path.read_bytes() if path.exists() else None
    bom, encoding = ini_format(before) if path.suffix == '.ini' and before else (b'', 'utf-8')
    if path.suffix == '.ini' and before and '\r\n' in before[len(bom):].decode(encoding):
        content = content.replace('\n', '\r\n')
    return Change(path, before, bom + content.encode(encoding))


def make_plan(engine, project, config, client, *, port=8000, uv=None, replace=False, usd=False):
    engine, project, config = Path(engine).resolve(), Path(project).resolve(), Path(config).resolve()
    build = read_object(engine / 'Engine/Build/Build.version')
    if (build.get('MajorVersion'), build.get('MinorVersion')) != (5, 8):
        raise ValueError('This setup requires UE 5.8; it does not install or upgrade the engine')
    if project.suffix != '.uproject':
        raise ValueError('Pass the actual .uproject file')
    data = read_object(project)
    if data.get('EngineAssociation') != '5.8':
        raise ValueError('EngineAssociation must be 5.8. Create a new 5.8 project or open a copy in 5.8 first.')
    check_binding(project)
    required = (*PLUGINS, 'USDImporter') if usd else PLUGINS
    available = {path.stem for path in (engine / 'Engine/Plugins').rglob('*.uplugin')}
    missing = set(required) - available
    if missing:
        raise ValueError('Required plugins absent from this engine: ' + ', '.join(sorted(missing)))
    plugins = data.setdefault('Plugins', [])
    if not isinstance(plugins, list) or any(not isinstance(p, dict) or not isinstance(p.get('Name'), str)
                                            for p in plugins):
        raise ValueError('Plugins must be an array of plugin objects with Name fields')
    names = [p['Name'] for p in plugins]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate plugin entries; fix the .uproject before applying setup')
    for name in required:
        entry = next((p for p in plugins if p['Name'] == name), None)
        if entry is None:
            plugins.append({'Name': name, 'Enabled': True})
        else:
            entry['Enabled'] = True
    entry = client_entry(client, port, uv)
    client_config = read_object(config) if config.exists() else {}
    servers = client_config.setdefault('mcpServers', {})
    if not isinstance(servers, dict):
        raise ValueError('mcpServers must be an object; configuration left unchanged')
    if SERVER in servers and servers[SERVER] != entry and not replace:
        raise ValueError('A different unreal-mcp entry exists; inspect it before using --replace-existing')
    # Do not create a second live connection beside Epic's optional native proxy.
    if 'unreal-mcp-proxy' in servers:
        raise ValueError('unreal-mcp-proxy already exists; use it or uninstall it before direct setup')
    servers[SERVER] = copy.deepcopy(entry)
    ini = project.parent / 'Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini'
    previous_ini = read_ini(ini) if ini.exists() else ''
    settings = set_ini_values(previous_ini, SECTION, {
        'bAutoStartServer': 'True', 'ServerPortNumber': str(port), 'ServerUrlPath': '/mcp',
        'bEnableToolSearch': 'True'})
    targets = [change(project, json.dumps(data, indent=2) + '\n'), change(ini, settings),
               change(config, json.dumps(client_config, indent=2) + '\n')]
    if len({item.path for item in targets}) != len(targets):
        raise ValueError('Client config must be separate from project and editor settings files')
    return targets


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            staged = Path(handle.name)
            handle.write(content)
        os.replace(staged, path)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def apply_plan(plan):
    changed = [item for item in plan if item.before != item.after]
    for item in changed:
        actual = item.path.read_bytes() if item.path.exists() else None
        if actual != item.before:
            raise ValueError(f'File changed since inspection; retry: {item.path}')
    written, report = [], []
    try:
        for item in changed:
            backup = None
            if item.before is not None:
                backup = item.path.with_name(f'{item.path.name}.{time.time_ns()}.bak')
                shutil.copy2(item.path, backup)
            atomic_write(item.path, item.after)
            written.append(item)
            report.append({'path': str(item.path), 'backup': str(backup) if backup else None})
    except OSError:
        for item in reversed(written):
            if item.before is None:
                item.path.unlink(missing_ok=True)
            else:
                atomic_write(item.path, item.before)
        raise
    return report


def editor_running():
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], check=True,
                            capture_output=True, text=True, timeout=15)
    return any(row and row[0].casefold() in ('unrealeditor.exe', 'unrealeditor-cmd.exe')
               for row in csv.reader(io.StringIO(result.stdout)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True, help='Installed UE_5.8 folder')
    parser.add_argument('--project', type=Path, required=True, help='Actual new/copy .uproject')
    parser.add_argument('--client', choices=['code', 'desktop'], required=True)
    parser.add_argument('--config', type=Path, help='Override actual client JSON path')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--usd', action='store_true', help='Also enable USDImporter')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--replace-existing', action='store_true')
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        parser.error('This installer targets native Windows. --help works on any platform.')
    uv = shutil.which('uv') if args.client == 'desktop' else None
    if args.client == 'desktop' and not uv:
        parser.error('Install uv, reopen PowerShell, then retry')
    config = args.config
    if config is None:
        if args.client == 'code':
            config = args.project.resolve().parent / '.mcp.json'
        elif os.environ.get('APPDATA'):
            config = Path(os.environ['APPDATA']) / 'Claude/claude_desktop_config.json'
        else:
            parser.error('APPDATA missing; pass the actual --config path')
    plan = make_plan(args.engine, args.project, config, args.client, port=args.port,
                     uv=Path(uv).resolve() if uv else None, replace=args.replace_existing, usd=args.usd)
    print(json.dumps({'mode': 'apply' if args.apply else 'inspect',
                      'files': [{'path': str(p.path), 'changed': p.before != p.after} for p in plan],
                      'unreal-mcp': client_entry(args.client, args.port, Path(uv).resolve() if uv else None)},
                     indent=2))
    if not args.apply:
        print('No files written. Save and close Unreal and the chosen client before --apply.')
        return
    if editor_running():
        raise RuntimeError('Save and close Unreal Editor before applying. No processes were stopped.')
    print(json.dumps(apply_plan(plan), indent=2))
    print('Open the project in UE 5.8. Restart Claude. Run pipeline.check next.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'SETUP FAILED: {exc}', file=sys.stderr)
        sys.exit(1)
