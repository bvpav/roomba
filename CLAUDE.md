# lunar-bitch

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

## Competition constraints

- Rover start size: ≤ 500×500×500 mm
- Rover weight: ≤ 25 kg, electric battery powered
- Fully autonomous — no communication during a round
- Penalty if rover contacts penalty field/wall more than 3 times or >20 seconds total

## Development branch

Active development happens on `claude/verify-arena-scene-ktrMj`. Push to this branch.
