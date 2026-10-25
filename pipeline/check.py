"""Check the native local HTTP MCP connection without spending model tokens."""

import argparse
import asyncio
import json
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or
            parsed.password or parsed.path != '/mcp' or parsed.query or parsed.fragment):
        raise ValueError('Use the local endpoint http://127.0.0.1:<port>/mcp')
    if not parsed.port:
        raise ValueError('Specify the actual local MCP port')


def tool_value(result):
    if result.isError:
        raise RuntimeError('MCP tool failed: ' + str(result.content))
    if result.structuredContent is not None:
        value = result.structuredContent
    else:
        text = '\n'.join(item.text for item in result.content if item.type == 'text')
        try:
            value = json.loads(text)
        except ValueError:
            value = text
    if isinstance(value, dict) and (value.get('success') is False or value.get('error')):
        raise RuntimeError(f'Unreal tool reported failure: {value}')
    return value


def require_catalog(value):
    catalog = value
    if isinstance(value, dict):
        if value.get('success') is False or value.get('error'):
            raise RuntimeError(f'Tool discovery failed: {value}')
        catalog = value.get('toolsets', value.get('Toolsets', value))
    if not catalog or catalog in ('[]', '{}'):
        raise RuntimeError('No toolsets returned. Enable AllToolsets and restart Unreal.')
    return value


async def inspect_session(session, read_tool=None, arguments=None):
    initialized = await session.initialize()
    response = await session.list_tools()
    names = [tool.name for tool in response.tools]
    if not names:
        raise RuntimeError('Connected but no tools. Enable AllToolsets and restart Unreal.')
    report = {'server': initialized.serverInfo.model_dump(), 'advertised_tools': names}
    if 'list_toolsets' in names:
        report['catalog'] = require_catalog(tool_value(await session.call_tool('list_toolsets', {})))
    else:
        report['catalog'] = {'direct_tools': names}
    if read_tool:
        if read_tool not in names:
            raise RuntimeError(f'{read_tool!r} is not an advertised tool; discover its schema first')
        report['read_result'] = tool_value(await session.call_tool(read_tool, arguments or {}))
    return report


async def inspect_server(url, read_tool=None, arguments=None):
    validate_url(url)
    async with asyncio.timeout(60):
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=45), follow_redirects=False) as http:
            async with streamable_http_client(url, http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    return await inspect_session(session, read_tool, arguments)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000/mcp')
    parser.add_argument('--read-tool', help='Optional confirmed read-only tool; e.g. call_tool after discovery')
    parser.add_argument('--arguments', default='{}', help='JSON arguments matching the discovered tool schema')
    args = parser.parse_args()
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        parser.error('--arguments must be a JSON object')
    report = asyncio.run(inspect_server(args.url, args.read_tool, arguments))
    print(json.dumps(report, indent=2))
    print('HTTP handshake and tool discovery passed. Asset operations and rendering require separate checks.')


if __name__ == '__main__':
    main()
