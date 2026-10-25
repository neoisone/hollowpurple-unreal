# Unreal and Blender workflow

Read README.md and docs/INTERCHANGE.md. Target Unreal **5.8**, using Epic's built-in `ModelContextProtocol` and `AllToolsets` plugins. Do not install a community C++ MCP server or downgrade to the old 5.7 Python bridge for this setup.

- Use `uv sync --frozen --python 3.11` and `uv run --frozen`. Inspect `pipeline.setup` before applying. Preserve the `blender` MCP entry and all unrelated configuration. Stop on conflicts instead of silently replacing a server.
- Run both applications with normal GUIs. Discover `unreal-mcp` with `list_toolsets`, then `describe_toolset`; invoke the discovered tool through `call_tool` with its real schema. Do not assume all individual Unreal tools appear in `tools/list`.
- Inspect the actual current project/level and Blender scene before changing either. Check engine and Blender versions, project path and active editor state. Use one intended Unreal editor per MCP port. A connected proxy or cached tool list is not proof that live calls work.
- Serialize Unreal calls. Wait for loading/compilation. Save a checkpoint before substantial edits, inspect results, and save after successful work. Do not reset an existing scene, overwrite existing assets, or run a factory-startup builder inside a live project.
- Use Blender for mesh authoring/rigging as appropriate; Unreal for scene assembly, Niagara, Sequencer, lighting and rendering. Use the existing Blender repo at https://github.com/neoisone/hollowpurple; consult its docs/REPOSITORIES.md for optional character/motion/effects tools.
- For static-mesh transfer use `pipeline.exchange prepare`, then source.py in the source app, `pipeline.exchange verify`, then target.py in the target app. Source/target scripts load helpers by absolute path; the checkout must remain available on this PC. Return and inspect real asset paths, dimensions, orientation, normals, UVs and materials. The Unreal import helper returns unsaved assets in a fresh /Game/Exchange/ folder. Save them only after inspection.
- Scripts can run using a discovered Unreal Python-capable tool; `ProgrammaticToolset.execute_tool_script` is documented by Epic, but discover its actual schema and execution environment first. The included scripts require editor Python with `unreal` available. In Blender use execute_blender_code. A file can be run with `import runpy; runpy.run_path(r"C:\actual\job\source.py")` in the correct application's interpreter.
- Never copy .uasset/.umap into Blender, treat .blend as a native Unreal asset, or promise identical procedural materials, Niagara systems, rig controls or simulations across engines. Bake/export the needed data, preserve authoring sources and rebuild native shaders/effects when required.
- Static helpers do not handle skeletal meshes, animations, whole scenes or assets with special licensing restrictions. Choose FBX/USD/Alembic according to the interchange guide and read the relevant official API before extending a workflow. Do not install every optional repository/dependency in advance.
- Keep local projects and exports outside source control. Keep the MCP endpoint on 127.0.0.1. Never disable firewall protection or stop unrelated processes to free a port. Do not publish assets, footage, credentials or new GitHub changes without a direct request.
- Verify low-cost previews for noise, glass/reflections, exposure, geometry intersections and motion before full renders. Configure Unreal's GPU separately from Blender's Cycles OptiX device. Report actual tool/test results, and explicitly label checks that were not run.

## Starter prompt

Paste into Claude Code from the project folder, or attach this file and the guides in Claude Desktop. Replace the placeholder paths with the actual paths on this PC:

```text
Set up and verify Claude control of both Unreal Engine 5.8 and Blender on this
Windows RTX 4090 workstation. The Unreal setup repo is <absolute repo path>,
the Unreal project is <absolute .uproject path>, and the Blender setup repo is
<absolute hollowpurple path>. Read their README and CLAUDE.md files and the
Unreal repo's docs/INTERCHANGE.md and docs/SOURCES_AND_ERRORS.md first.

Use Epic's native UE 5.8 MCP plus the Blender MCP already configured. Preserve
both server entries and unrelated settings. Use the existing Python scripts and
frozen dependencies; do not redesign either bridge or install a community C++
plugin. Inspect the setup before applying it. Show any conflicting server entry
and wait for my choice before replacement. Do not upgrade an original project
in place or reset my active Blender scene.

Verify Unreal's MCP handshake, discover toolsets and schemas, and make a real
read-only query of the intended project/current level. Verify Blender's add-on,
scene inspection and a small Python execution too. Report what actually passed.
Then, in a disposable project/scene, test one static mesh Blender-to-Unreal and
one static mesh Unreal-to-Blender using the transfer helpers and a shared local
exchange folder. Verify dimensions, orientation, normals, UVs and material
limits. Do not claim native shaders or rig controls round-trip automatically.

Keep Unreal calls sequential and save checkpoints before edits. State every
manual step or unverified item clearly. After the connections and transfer test,
wait for my creative scene request instead of starting an unrelated project.
```
