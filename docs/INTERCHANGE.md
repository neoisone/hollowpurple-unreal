# Blender ↔ Unreal through Claude

Claude is the coordinator. The two MCP connections control two different applications; neither MCP turns one application's native project format into the other's. Both applications and Claude run on the same Windows PC for this setup. A shared local folder carries exported data. The repository stores code and instructions, not production assets.

## Choose what must travel

| Need | Format/workflow | Limits to verify |
| --- | --- | --- |
| One static mesh | Included FBX helpers, either direction | Dimensions, origin, axes, normals, UVs, material slots; rebuild detailed materials |
| Skeletal mesh and baked animation | FBX with explicit skeleton/export and import settings | Bone axes/names, root scale, rest pose, root motion, frame rate, skin weights; not handled by the static helpers |
| Scene hierarchy, cameras, layout, supported animation | USD, with Unreal USDImporter enabled | Supported prims, metersPerUnit/upAxis, texture paths, USD Preview Surface; application-specific shaders need work |
| Baked deforming geometry | Alembic, task-specific importer/exporter | Topology, frame range/rate, cache size; no editable original simulation or rig |
| Textures/material look | Image files plus rebuilt native materials; limited FBX/USD material interchange | Color space, normal conventions, roughness/metallic channels, transparency and emission |
| Niagara, Blender geometry nodes or physics simulations | Keep native setup, transfer baked output where supported | No general editable round trip; author a native equivalent for the destination |

Epic documents FBX 2020.2 for its FBX pipeline. Blender's exporter can emit a different FBX revision; file recognition alone is not compatibility proof. The included Blender smoke test emitted FBX 7400. Test the particular asset in UE 5.8 before committing a production pipeline.

Epic's Send to Unreal and UE to Rigify are relevant optional tools: [official repository](https://github.com/EpicGames/BlenderTools), [Send to Unreal docs](https://epicgames.github.io/BlenderTools/send2ue/). They provide richer transfer/retargeting workflows. Their older documented Blender baseline does not establish compatibility with our Blender 5.2 + UE 5.8 pair. Validate a pinned version before adding them; the core MCP setup does not depend on them.

## Static mesh: Blender → Unreal

1. Save the original Blender project. Choose one mesh in Object Mode; armature-modified meshes are rejected. The helper expects Blender `scale_length = 1.0`, where one unit represents one metre. Normalize a copy if necessary. Use an asymmetric test object with a marked front/top, not only a cube.
2. From the Unreal setup repo in PowerShell:

```powershell
uv run --frozen python -m pipeline.exchange prepare --direction blender-to-unreal --exchange "C:\HollowpurpleExchange" --name SM_Desk --source Desk
```

3. Use the returned `job_dir`. Through Blender MCP's `execute_blender_code`, execute that directory's source script:

```python
import runpy
runpy.run_path(r"C:\HollowpurpleExchange\<actual-job-directory>\source.py")
```

This exports only that mesh, evaluates mesh modifiers, disables animation export, includes unit information, and restores the previous selection. It refuses to overwrite an existing FBX. It does not save/reset the scene.

4. Verify the nonempty export and record its hash:

```powershell
uv run --frozen python -m pipeline.exchange verify "C:\HollowpurpleExchange\<actual-job-directory>"
```

5. Through Unreal MCP, discover a Python-capable tool and its schema. Execute `target.py` in the editor's Python environment with the same `runpy.run_path` pattern. If a tool exposes a restricted scripting environment, inspect its documentation rather than assuming arbitrary `unreal` imports work. As a manual fallback, Unreal's **File → Execute Python Script** can run the target script.
6. The helper verifies the file hash and imports into a **fresh `/Game/Exchange/<job>` folder**. It uses `AssetImportTask` with the project's active importer and does not toggle global Interchange flags. Names/options can differ between import pipelines: use the **returned actual asset paths**, not an assumed name. It requires a resulting StaticMesh and returns assets unsaved. If import fails, inspect the Output Log and any partial assets before retrying with a new transfer.
7. Inspect the mesh and a small lit preview; then save the imported assets through Unreal's asset API/editor. Never move `.uasset` files with filesystem operations to reorganize content; use Unreal's asset APIs.

## Static mesh: Unreal → Blender

1. Inspect the source asset. Use the path of a **StaticMesh asset** from the Content Browser, for example `/Game/Props/SM_Chair.SM_Chair`. This exports the asset in its local space, not an actor's level placement. Only transfer assets you have permission to use/export.
2. Prepare a new job:

```powershell
uv run --frozen python -m pipeline.exchange prepare --direction unreal-to-blender --exchange "C:\HollowpurpleExchange" --name SM_Chair --source /Game/Props/SM_Chair.SM_Chair
```

3. Run `source.py` in Unreal editor Python via its discovered MCP tool. The helper uses `StaticMeshExporterFBX`, `AssetExportTask` and `FbxExportOption`, refusing an existing output file.
4. Run `pipeline.exchange verify` with the returned job directory.
5. Run `target.py` through Blender MCP. It verifies the hash, imports without animation and puts the new objects in their own `Exchange_<job>` collection. It refuses to import that same job twice. Existing Blender objects remain intact; imported names may receive Blender's numeric suffixes.
6. Inspect and save the new Blender file/checkpoint. Use USD when you need level hierarchy, transforms or cameras instead of one asset in local space.

## Acceptance on the Windows PC

Run this in disposable new projects, with the intended editors open. The instructions request these checks; current CI does not execute Unreal.

1. `pipeline.check` passes against the **real UE 5.8 editor**, and Claude makes a read-only query confirming the intended project and level. Blender's `pipeline.check_mcp` also passes from its own repo/environment.
2. Export an asymmetric Blender mesh with known 1 m and 2 m dimensions, a front/top marker and a simple UV checker. Import into Unreal. Check dimensions in centimetres (100 cm and 200 cm), orientation, origin, normals and UVs. Check returned asset paths and save only after inspection.
3. Export that Unreal static mesh in a new reverse-direction job and import into Blender. Check dimensions/orientation again. Inspect an actual preview in both applications. The macOS Blender-only smoke result is not evidence of this full round trip.
4. Test one relevant animation/USD/cache separately before relying on it for a scene. Check frame rate and frame range. Material graph identity and procedural simulation editability are not expected to transfer automatically.
5. Restart Unreal, reconnect Claude if required, and repeat a real read-only editor call. A proxy catalog is not sufficient evidence of recovery.

Exports and manifests are local. Each job gets a new directory and Unreal destination. Hash verification detects a changed export between stages; it does not validate geometry quality or license permissions. Keep authoring sources and a clear direction of ownership for each asset to avoid overwriting a good source with a baked derivative.
