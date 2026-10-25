# Official references and troubleshooting

## Version and architecture

The selected target is **UE 5.8**, using the native engine server. It supersedes the earlier request for a 5.7.4 bridge. The installer verifies the installed `Engine/Build/Build.version`, requires project association `5.8`, and checks that the required plugin descriptors exist. It supports Launcher projects on native Windows. It does not upgrade projects, patch an engine installation, download Unreal or build C++ plugins.

The mature integration options considered were Epic's native MCP in 5.8, the Python remote-execution API shipped in 5.7, and third-party C++ MCP plugins. Native 5.8 avoids maintaining a separate Unreal protocol implementation or plugin build. The external Python SDK here is used for validation and Desktop transport adaptation; the engine owns tools and their schemas.

The Blender configuration is independent. Its existing user-scope stdio server can coexist with a project-scope Unreal HTTP server in Claude Code. Desktop merges both entries in its local JSON file. Each application retains its own interpreter and renderer. The transfer helpers use standard files between them.

## Sources

Prefer versioned documentation and the APIs actually present in the installed engine. Official guides generally document the **5.8 minor version**, not every patch. Inspect discovered tool schemas and the local engine build rather than guessing patch-specific behavior.

- [Epic: UE 5.8 release announcement](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available): availability and the native Experimental MCP feature.
- [Epic: Unreal MCP in UE 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-mcp-in-unreal-editor?application_version=5.8): plugins, local HTTP transport, tool search, commands, defaults, limitations and serialized editor calls.
- [Epic's Claude Code skill plugin](https://github.com/EpicGames/unreal-engine-skills-for-claude-code-plugin): official installation, Windows Bash hook requirement and live tool-discovery workflow.
- [Epic's setup reference](https://github.com/EpicGames/unreal-engine-skills-for-claude-code-plugin/blob/main/skills/unreal-mcp/references/setup.md): `.uproject` plugin identifiers, per-user editor settings, project config and optional native proxy.
- [Epic's operation/recovery reference](https://github.com/EpicGames/unreal-engine-skills-for-claude-code-plugin/blob/main/skills/unreal-mcp/references/operations.md): stopped editors, stale catalogs and reconnect behavior.
- [Epic: character encoding](https://dev.epicgames.com/documentation/unreal-engine/character-encoding-in-unreal-engine?lang=en-US) and [configuration branches](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Core/FConfigBranch): Unreal INI encodings and saved configuration layers. Setup handles UTF-16 BOM files and checks both project Config and Saved/Config for non-loopback overrides.
- [Epic: Python scripting in UE 5.8](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python?application_version=5.8): editor-only Python, plugin enablement, paths, asset APIs and execution methods.
- [Epic: FBX pipeline](https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-content-pipeline?application_version=5.8): supported content and FBX version compatibility.
- [Epic: USD in Unreal](https://dev.epicgames.com/documentation/en-us/unreal-engine/universal-scene-description-in-unreal-engine?application_version=5.8): supported scene data, USD Importer, Python workflows and limitations.
- [Epic: StaticMeshExporterFBX API](https://dev.epicgames.com/documentation/unreal-engine/API/Editor/UnrealEd/UStaticMeshExporterFBX): static mesh FBX exporter.
- [EpicGames/BlenderTools](https://github.com/EpicGames/BlenderTools) and [Send to Unreal quickstart](https://epicgames.github.io/BlenderTools/send2ue/introduction/quickstart): optional richer Blender→Unreal transfer; verify current version compatibility before adding it.
- [Blender export operators](https://docs.blender.org/api/current/bpy.ops.export_scene.html) and [Blender import operators](https://docs.blender.org/api/current/bpy.ops.import_scene.html): FBX operator parameters. Check the API of the installed Blender when current docs differ.
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp): HTTP and stdio servers, configuration scope, `--mcp-config` and server approval.
- [Claude Desktop local MCP setup](https://modelcontextprotocol.io/docs/develop/connect-local-servers): local server configuration and restart behavior.
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0): the pinned 1.x client/server SDK used by checks and fixtures.
- [mcp-proxy](https://github.com/sparfenyuk/mcp-proxy): stdio↔Streamable HTTP adaptation. The lockfile pins 0.13.0 and transitive dependencies.
- [uv installation](https://docs.astral.sh/uv/getting-started/installation/) and [uv projects](https://docs.astral.sh/uv/guides/projects/): managed Python and frozen project environments.

## Errors to resolve before spending model turns

| Symptom | Cause/check | Action |
| --- | --- | --- |
| `ModelContextProtocol` missing | UE 5.7.4 selected, incomplete install, or different engine path | Select installed 5.8 and the actual new/copy project. Do not copy 5.8 plugins into 5.7.4. |
| Setup rejects `EngineAssociation` | Project still belongs to another engine or uses a source-build GUID | Create/open a copy in Launcher 5.8. Source-build GUID automation is outside this helper's scope. |
| Connected, no tools | Server plugin alone has no providers | Enable `AllToolsets`, restart Unreal, then check discovery. |
| Only three tools shown | Tool search is on | Use `list_toolsets` → `describe_toolset` → `call_tool`; do not reinstall the server. |
| Connection refused / HTTP check fails | Editor closed, startup disabled, loading not complete, wrong port/path | Open intended project, inspect Output Log, run `ModelContextProtocol.StartServer`, verify the configured endpoint. |
| Port 8000 busy | Another project/server/service owns it | Choose another port in this setup and checker. Do not stop an unrelated process or open a public port. |
| Config conflict | Different `unreal-mcp`, native proxy entry or malformed JSON | Inspect the actual file and keep its backup. Choose one Unreal connection; use replacement only deliberately. |
| Unreal tools appear but calls fail after restart | Client catalog/session is stale | Reconnect/restart the chosen Claude client, discover tools again, then verify a live read-only call. |
| Claude Desktop sees no local server | Wrong config path, Desktop not restarted, uv path invalid, repo moved | Close/reopen Desktop; inspect `%APPDATA%\Claude\claude_desktop_config.json`, rerun frozen setup at the new path. |
| Blender disappears from Claude Code | Strict MCP configuration or different client/scope used | Run without `--strict-mcp-config`; verify Blender is installed in this same client at user scope. |
| Plugin hook says Bash missing | Epic skill plugin's hook is a Bash script | Install Git for Windows and verify Bash on PATH; native MCP itself can work without the hook. |
| Python script fails in a discovered tool | Wrong interpreter/context, plugin missing or changed schema | Discover the real tool schema; confirm `unreal` is available and PythonScriptPlugin enabled. Use File → Execute Python Script as a manual diagnostic. |
| Import returns no StaticMesh | Active importer/settings rejected the file or produced another asset type | Inspect Output Log and partial assets. Test the FBX in the editor UI; use a new job for retries. Do not globally disable Interchange to hide the error. |
| Size/orientation wrong | Unit/axis mismatch or project import defaults | Test a marked asymmetric mesh; normalize a source copy, check centimetres/metres and actual importer settings. |
| Target rejects hash/missing export | Source script has not run, verify skipped, or file changed | Run source → verify → target in order. Use a new job if the source changed. |
| Material or effect looks different | Native procedural graphs/simulation did not transfer | Export textures/baked data as needed and rebuild the destination's native shader/effect. |
| Render noisy or GPU unclear | Connection check does not validate rendering | Inspect a short render; check the actual renderer, samples/denoising and GPU activity independently. |

The repository's tests exercise transport and file/config logic without an LLM. They do not prove Epic's engine tools, asset conversion or the target GPU work. Keep those limits explicit in any handoff or completion report.
