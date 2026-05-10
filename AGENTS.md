# ROOMBA

Autonomous lunar rover for the **EnduroSat Endurance Space Race 2026** (July 13, Sofia, Bulgaria).

Goal: autonomously collect and deposit 40 resources from a resource field into a deposit pit within 8 minutes.

## Repository structure

```
simulation/     Godot 4.6 testing environment (small, secondary concern)
```

More directories will be added as the project grows (rover firmware, perception, planning, etc.).

## Simulation

The Godot simulation (`simulation/`) is a **test environment only** — used for validating algorithms and arena geometry before deploying to hardware. It is not the main deliverable.

- Engine: Godot 4.6, Jolt Physics, Forward Plus rendering
- Main scene: `simulation/field.tscn` — arena recreation
- Rover scene: `simulation/rover.tscn` — currently a placeholder bounding box

The arena matches the competition spec exactly (480×230 cm inner footprint). The resource field terrain and resource objects are not yet implemented.

### GDScript style

Follow the [GDScript style guide](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_styleguide.html) strictly (PEP 8-inspired).

- **No abbreviations** in variable/function names unless the abbreviation is widely recognized and the full name is unreasonably long (e.g. `id`, `url`, `html` are fine).
- **Strict typing everywhere** — use type inference (`:=`) for local variables and members where the type is unambiguous. Use explicit type hints where inference is not possible: function parameters, return types, and `@onready` node references. Use typed arrays (`Array[T]`) instead of bare `Array`.
- **Scene node access** — prefer unique names (`%NodeName`) over `$Path/To/Node`. Store node references in private `@onready` members with explicit type hints (e.g. `@onready var _sprite: Sprite2D = %Sprite2D`).
- **Double blank lines** between methods and between each section from the definition order below.
- **Definition order** (per official Godot style guide):
  1. `@tool`, `@icon`, `@static_unload`
  2. `class_name`
  3. `extends`
  4. Doc comments (`##`)
  5. Signals
  6. Enums
  7. Constants
  8. Static variables
  9. `@export` variables
  10. Regular variables
  11. `@onready` variables
  12. `_static_init()`
  13. Remaining static methods
  14. Overridden built-in virtual methods (lifecycle order: `_init`, `_enter_tree`, `_ready`, `_process`, `_physics_process`, then others)
  15. Overridden custom methods
  16. Remaining methods (public before private)
  17. Inner classes

## Competition constraints

- Rover start size: ≤ 500×500×500 mm
- Rover weight: ≤ 25 kg, electric battery powered
- Fully autonomous — no communication during a round
- Penalty if rover contacts penalty field/wall more than 3 times or >20 seconds total

## Development branch

Active development happens on `claude/verify-arena-scene-ktrMj`. Push to this branch.
