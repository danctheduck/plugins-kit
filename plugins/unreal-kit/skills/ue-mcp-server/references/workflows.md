# MCP Workflow Recipes

Multi-step recipes that combine multiple MCP tool domains for common authoring
tasks. They are workflow summaries, not a server schema.

Each recipe below names the goal, lists the tool calls in order, and notes the post-conditions to verify before declaring the workflow complete.

## Create a Blueprint from scratch

1. `manage_blueprint` -> `create` with name, parent class, and folder.
2. `manage_blueprint` -> `add_component` for each component the BP needs.
3. `manage_blueprint` -> `create_node` + `connect_pins` to author graph logic.
4. Save only the Blueprint: pass `save:true` on the last graph mutation, and `applyAndSave:true` on `add_component`. `control_editor` -> `save_all` is the fallback when no save parameter applies.
5. Verify the `.uasset`'s modification time or checksum changed since before the edit; existence alone proves nothing.

## Build a level shell

1. `manage_level` -> `create` with name and folder.
2. `manage_lighting` -> `spawn_light` for primary light sources.
3. `control_actor` -> `spawn` for placeable actors (player start, geometry primitives, etc.).
4. `manage_lighting` -> `build` to bake lighting.
5. `manage_level` -> `save` to write the level. `control_editor` -> `save_all` is the fallback when the level save does not apply.

## Material setup

1. `manage_asset` -> `create_material` with name and folder.
2. `manage_material_authoring` -> `add_node` + `connect` to author the graph.
3. Save only the material: pass `save:true` on the last `manage_material_authoring` call. `control_editor` -> `save_all` is the fallback when no save parameter applies.
4. Verify the `.uasset`'s modification time or checksum changed since before the edit.
5. (Optional) `manage_asset` -> `create_material_instance` for variants.

## PIE drive for testing

1. `control_editor` -> `play` to start PIE.
2. `control_editor` -> `console_command` to drive in-game state (cheats, teleport, skip onboarding).
3. `inspect` to read runtime actor state.
4. `control_editor` -> `stop_pie` when runtime checks are complete.
5. `control_editor` -> `screenshot` for an editor-state capture. This does not
   capture the runtime state; runtime visual capture remains unverified until
   a supported server operation is established.
