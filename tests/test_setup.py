"""Configuration invariants: preserve Blender, preflight before writes, exact backups."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.engine = self.root / 'UE_5.8'
        build = self.engine / 'Engine/Build/Build.version'
        build.parent.mkdir(parents=True)
        build.write_text(json.dumps({'MajorVersion': 5, 'MinorVersion': 8, 'PatchVersion': 1}))
        for name in setup.PLUGINS:
            plugin = self.engine / f'Engine/Plugins/Test/{name}/{name}.uplugin'
            plugin.parent.mkdir(parents=True)
            plugin.write_text('{}')
        self.project = self.root / 'My Film/Film.uproject'
        self.project.parent.mkdir()
        self.project.write_text(json.dumps({'EngineAssociation': '5.8', 'Plugins': [
            {'Name': 'KeepMe', 'Enabled': True},
            {'Name': 'ModelContextProtocol', 'Enabled': False, 'Extra': 'keep'}]}))
        self.config = self.root / 'client.json'
        self.config.write_bytes(b'{"theme":"dark","mcpServers":{"blender":{"command":"keep"}}}\n')

    def plan(self, **kwargs):
        return setup.make_plan(self.engine, self.project, self.config, 'code', **kwargs)

    def test_dry_run_preserves_all_files_and_creates_no_settings(self):
        before = self.config.read_bytes(), self.project.read_bytes()
        plan = self.plan()
        self.assertEqual(len(plan), 3)
        self.assertEqual((self.config.read_bytes(), self.project.read_bytes()), before)
        self.assertFalse((self.project.parent / 'Saved').exists())

    def test_apply_keeps_blender_and_plugin_fields_and_backs_up_original_bytes(self):
        original = self.config.read_bytes()
        plan = self.plan()
        result = setup.apply_plan(plan)
        config = json.loads(self.config.read_text())
        self.assertEqual(config['mcpServers']['blender'], {'command': 'keep'})
        self.assertEqual(config['theme'], 'dark')
        self.assertEqual(config['mcpServers']['unreal-mcp'],
                         {'type': 'http', 'url': 'http://127.0.0.1:8000/mcp'})
        plugins = json.loads(self.project.read_text())['Plugins']
        self.assertIn({'Name': 'KeepMe', 'Enabled': True}, plugins)
        self.assertIn({'Name': 'ModelContextProtocol', 'Enabled': True, 'Extra': 'keep'}, plugins)
        backup = next(item['backup'] for item in result if item['path'] == str(self.config))
        self.assertEqual(Path(backup).read_bytes(), original)
        self.assertEqual(setup.apply_plan(self.plan()), [])

    def test_574_and_missing_plugin_fail_before_any_write(self):
        build = self.engine / 'Engine/Build/Build.version'
        build.write_text('{"MajorVersion":5,"MinorVersion":7,"PatchVersion":4}')
        with self.assertRaisesRegex(ValueError, '5.8'):
            self.plan()
        build.write_text('{"MajorVersion":5,"MinorVersion":8,"PatchVersion":0}')
        next(self.engine.rglob('AllToolsets.uplugin')).unlink()
        with self.assertRaisesRegex(ValueError, 'AllToolsets'):
            self.plan()
        self.assertNotIn('unreal-mcp', self.config.read_text())

    def test_config_conflict_and_invalid_shapes_never_overwrite(self):
        for text in ['{broken', '[]', '{"mcpServers":[]}',
                     '{"mcpServers":{"unreal-mcp":{"command":"old"}}}']:
            self.config.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.plan()
            self.assertEqual(self.config.read_text(), text)

    def test_replace_is_explicit_and_preserves_blender(self):
        self.config.write_text('{"mcpServers":{"blender":{"command":"keep"},'
                               '"unreal-mcp":{"command":"old"}}}')
        setup.apply_plan(self.plan(replace=True))
        self.assertEqual(json.loads(self.config.read_text())['mcpServers']['blender']['command'], 'keep')

    def test_editor_ini_preserves_other_sections_and_replaces_duplicate_keys(self):
        old = ('; keep this\n[Elsewhere]\nServerPortNumber=9999\n'
               f'[{setup.SECTION}]\nbAutoStartServer=False\nServerPortNumber=9000\n'
               'ServerPortNumber=9001\nExtra=True\n')
        ini = self.project.parent / 'Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini'
        ini.parent.mkdir(parents=True)
        ini.write_text(old)
        setup.apply_plan(self.plan(port=8123))
        text = ini.read_text()
        self.assertIn('[Elsewhere]\nServerPortNumber=9999', text)
        self.assertIn('Extra=True', text)
        self.assertNotIn('ServerPortNumber=900', text)
        self.assertIn('ServerPortNumber=8123', text)

    def test_nonlocal_http_bind_and_wrong_engine_association_are_rejected(self):
        ini = self.project.parent / 'Config/DefaultEngine.ini'
        ini.parent.mkdir()
        ini.write_text('[HTTPServer.Listeners]\nDefaultBindAddress=0.0.0.0\n')
        with self.assertRaisesRegex(ValueError, 'loopback'):
            self.plan()
        ini.unlink()
        self.project.write_text('{"EngineAssociation":"5.7"}')
        with self.assertRaisesRegex(ValueError, 'EngineAssociation'):
            self.plan()

    def test_desktop_proxy_is_pinned_and_handles_paths_with_spaces(self):
        entry = setup.client_entry('desktop', 8123, Path('C:/Tools With Spaces/uv.exe'))
        self.assertEqual(Path(entry['command']), Path('C:/Tools With Spaces/uv.exe'))
        self.assertIn('--frozen', entry['args'])
        self.assertIn('mcp-proxy', entry['args'])
        self.assertEqual(entry['args'][-2:], ['streamablehttp', 'http://127.0.0.1:8123/mcp'])

    def test_desktop_launch_keeps_custom_managed_python_location(self):
        location = str(self.root / 'Managed Python')
        with patch.dict(os.environ, {'UV_PYTHON_INSTALL_DIR': location}):
            entry = setup.client_entry('desktop', 8000, Path('uv'))
        self.assertEqual(entry['env'].get('UV_PYTHON_INSTALL_DIR'), location)

    def test_write_failure_restores_original_files(self):
        original = self.config.read_bytes(), self.project.read_bytes()
        real_write = setup.atomic_write
        calls = 0

        def fail_second(path, content):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('disk full')
            real_write(path, content)

        with patch.object(setup, 'atomic_write', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'disk full'):
                setup.apply_plan(self.plan())
        self.assertEqual((self.config.read_bytes(), self.project.read_bytes()), original)

    def test_utf16_unreal_ini_is_read_and_preserved_with_its_backup(self):
        ini = self.project.parent / 'Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini'
        ini.parent.mkdir(parents=True)
        original = ('; résumé\r\n[Other]\r\nKeep=True\r\n'
                    f'[{setup.SECTION}]\r\nbAutoStartServer=False\r\n').encode('utf-16')
        ini.write_bytes(original)
        config_ini = self.project.parent / 'Config/DefaultEngine.ini'
        config_ini.parent.mkdir()
        config_ini.write_bytes('[HTTPServer.Listeners]\nDefaultBindAddress=127.0.0.1\n'.encode('utf-16'))
        result = setup.apply_plan(self.plan())
        after = ini.read_bytes().decode('utf-16')
        self.assertIn('; résumé\r\n[Other]\r\nKeep=True', after)
        self.assertIn('bAutoStartServer=True', after)
        backup = next(item['backup'] for item in result if item['path'] == str(ini))
        self.assertEqual(Path(backup).read_bytes(), original)

    def test_utf16_big_endian_settings_keep_their_bom_and_unicode(self):
        ini = self.project.parent / 'Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini'
        ini.parent.mkdir(parents=True)
        original = b'\xfe\xff' + '[Other]\nLabel=部屋\n'.encode('utf-16-be')
        ini.write_bytes(original)
        setup.apply_plan(self.plan())
        after = ini.read_bytes()
        self.assertTrue(after.startswith(b'\xfe\xff'))
        self.assertIn('Label=部屋', after[2:].decode('utf-16-be'))
        self.assertIn('bAutoStartServer=True', after[2:].decode('utf-16-be'))

    def test_saved_nonlocal_listener_override_is_rejected_before_writes(self):
        ini = self.project.parent / 'Saved/Config/WindowsEditor/Engine.ini'
        ini.parent.mkdir(parents=True)
        ini.write_text('[HTTPServer.Listeners]\nDefaultBindAddress=0.0.0.0\n')
        before = self.config.read_bytes(), self.project.read_bytes()
        with self.assertRaisesRegex(ValueError, 'loopback'):
            self.plan()
        self.assertEqual((self.config.read_bytes(), self.project.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
