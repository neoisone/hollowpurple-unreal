"""Isolated MCP HTTP fixture; it does not simulate Unreal's engine APIs."""

import argparse
from mcp.server.fastmcp import FastMCP

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, required=True)
args = parser.parse_args()
server = FastMCP('transport-fixture', host='127.0.0.1', port=args.port)


@server.tool()
def list_toolsets() -> dict:
    return {'toolsets': [{'name': 'Fixture', 'description': 'Transport test only'}]}


@server.tool()
def read_scene() -> dict:
    return {'project': 'Transport fixture', 'actors': 0}


server.run(transport='streamable-http')
