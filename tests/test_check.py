import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

from pipeline import check
from pipeline.setup import client_entry


class ResultTests(unittest.TestCase):
    def test_errors_and_empty_catalog_do_not_pass_as_working_tools(self):
        with self.assertRaises(RuntimeError):
            check.tool_value(CallToolResult(isError=True, content=[TextContent(type='text', text='bad')]))
        with self.assertRaises(RuntimeError):
            check.require_catalog({'toolsets': []})
        with self.assertRaises(RuntimeError):
            check.require_catalog({'success': False, 'error': 'not ready'})

    def test_only_loopback_http_endpoint_is_accepted(self):
        for url in ['http://0.0.0.0:8000/mcp', 'http://example.com/mcp',
                    'http://user:secret@127.0.0.1:8000/mcp', 'http://127.0.0.1:8000/other']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                check.validate_url(url)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.log = tempfile.TemporaryFile()
        cls.process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('mcp_fixture.py')),
                                        '--port', str(cls.port)], stdout=cls.log, stderr=cls.log)
        cls.addClassCleanup(cls.log.close)
        cls.addClassCleanup(cls.stop_fixture)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                cls.log.seek(0)
                raise RuntimeError(cls.log.read().decode())
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError('Transport fixture did not start')
        cls.url = f'http://127.0.0.1:{cls.port}/mcp'

    @classmethod
    def stop_fixture(cls):
        cls.process.terminate()  # Only the fixture process started by this test.
        try:
            cls.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=10)

    async def test_real_http_handshake_catalog_and_read_call(self):
        report = await check.inspect_server(self.url, 'read_scene', {})
        self.assertEqual(report['server']['name'], 'transport-fixture')
        self.assertEqual(report['read_result']['actors'], 0)
        self.assertEqual(report['catalog']['toolsets'][0]['name'], 'Fixture')

    async def test_desktop_stdio_proxy_reaches_the_same_http_server(self):
        uv = shutil.which('uv')
        self.assertIsNotNone(uv, 'Run tests under uv as documented')
        entry = client_entry('desktop', self.port, Path(uv).resolve())
        params = StdioServerParameters(**entry)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                report = await check.inspect_session(session, 'read_scene', {})
        self.assertEqual(report['read_result']['project'], 'Transport fixture')


if __name__ == '__main__':
    unittest.main()
