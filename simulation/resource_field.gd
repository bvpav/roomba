@tool
extends MeshInstance3D

## Procedural terrain for the 400×200 cm resource field.
## Runs in-editor (@tool) and at runtime.


const FIELD_WIDTH := 4.0  # 400 cm in metres (local X axis)
const FIELD_DEPTH := 2.0  # 200 cm in metres (local Z axis)
const CELLS_X := 16
const CELLS_Z := 8
const NOISE_SEED := 12345
const MAX_SLOPE_TAN := 0.57735  # tan(30°)


var _saved_mesh: ArrayMesh
var _saved_shape: ConcavePolygonShape3D


@onready var _collision_shape: CollisionShape3D = %CollisionShape3D


func _ready() -> void:
	_build()


func _notification(what: int) -> void:
	if what == NOTIFICATION_EDITOR_PRE_SAVE:
		_saved_mesh = mesh as ArrayMesh
		_saved_shape = _collision_shape.shape as ConcavePolygonShape3D
		mesh = null
		_collision_shape.shape = null
	elif what == NOTIFICATION_EDITOR_POST_SAVE:
		mesh = _saved_mesh
		_collision_shape.shape = _saved_shape


func _build() -> void:
	var cell_w := FIELD_WIDTH / CELLS_X
	var cell_d := FIELD_DEPTH / CELLS_Z
	var max_dy_x := cell_w * MAX_SLOPE_TAN
	var max_dy_z := cell_d * MAX_SLOPE_TAN

	# ── 1. Accumulate noise-driven slopes from the base-field edge ────────
	# Instead of generating small absolute heights, each step adds a
	# noise-driven delta clamped to ±max_dy_x.  This lets terrain build
	# cumulative hills that use the full 30° slope budget.
	var noise := FastNoiseLite.new()
	noise.seed = NOISE_SEED
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.35

	# h[z_idx][x_idx]
	var h: Array[Array] = []
	for jj in range(CELLS_Z + 1):
		var row: Array[float] = []
		row.append(0.0)
		for ii in range(1, CELLS_X + 1):
			var nx := -FIELD_WIDTH * 0.5 + ii * cell_w
			var nz := -FIELD_DEPTH * 0.5 + jj * cell_d
			# Noise in [-1, 1] drives slope — terrain can go up or down
			var slope := noise.get_noise_2d(nx, nz) * max_dy_x
			row.append(row[ii - 1] + slope)
		h.append(row)

	# Shift the entire heightmap so the global minimum sits at 0.
	# This ensures no vertex is negative and ii=0 stays level with base
	# field only if it happens to be the lowest — otherwise it rises too,
	# which is fine (the base-field edge just gets a small step up).
	var min_h: float = h[0][0]
	for jj in range(CELLS_Z + 1):
		for ii in range(CELLS_X + 1):
			if h[jj][ii] < min_h:
				min_h = h[jj][ii]
	for jj in range(CELLS_Z + 1):
		for ii in range(CELLS_X + 1):
			h[jj][ii] -= min_h

	# ── 2. Enforce 30° slope constraint (iterative relaxation) ────────────
	# The X-slopes are already bounded by construction, but Z-relaxation
	# may violate X, so enforce both.  ii=0 stays pinned at 0.
	for _pass in range(8):
		for jj in range(CELLS_Z + 1):
			for ii in range(CELLS_X + 1):
				if ii == 0:
					h[jj][ii] = 0.0
					continue
				var diff_x: float = h[jj][ii] - h[jj][ii - 1]
				if absf(diff_x) > max_dy_x:
					h[jj][ii] = h[jj][ii - 1] + signf(diff_x) * max_dy_x
				if jj > 0:
					var diff_z: float = h[jj][ii] - h[jj - 1][ii]
					if absf(diff_z) > max_dy_z:
						h[jj][ii] = h[jj - 1][ii] + signf(diff_z) * max_dy_z
				h[jj][ii] = maxf(h[jj][ii], 0.0)

	# ── 3. Build ArrayMesh with herringbone triangulation ──────────────────
	var surface_tool := SurfaceTool.new()
	surface_tool.begin(Mesh.PRIMITIVE_TRIANGLES)

	for jj in range(CELLS_Z):
		for ii in range(CELLS_X):
			var x0 := -FIELD_WIDTH * 0.5 + ii * cell_w
			var x1 := x0 + cell_w
			var z0 := -FIELD_DEPTH * 0.5 + jj * cell_d
			var z1 := z0 + cell_d

			var v00 := Vector3(x0, h[jj][ii], z0)
			var v10 := Vector3(x1, h[jj][ii + 1], z0)
			var v11 := Vector3(x1, h[jj + 1][ii + 1], z1)
			var v01 := Vector3(x0, h[jj + 1][ii], z1)

			# Herringbone: alternate the diagonal each cell to avoid
			# directional physics bias.
			if jj % 2 != 0:
				# NW-SE diagonal split
				_add_tri(surface_tool, v00, v10, v11)
				_add_tri(surface_tool, v00, v11, v01)
			else:
				# NE-SW diagonal split
				_add_tri(surface_tool, v00, v10, v01)
				_add_tri(surface_tool, v10, v11, v01)

	var arr_mesh := surface_tool.commit()
	mesh = arr_mesh

	# ── 5. ConcavePolygonShape3D on child StaticBody3D ─────────────────────
	_update_collision(arr_mesh)


## Adds a triangle with a shared per-face normal (flat / faceted shading).
func _add_tri(surface_tool: SurfaceTool, v0: Vector3, v1: Vector3, v2: Vector3) -> void:
	var normal := (v2 - v0).cross(v1 - v0).normalized()

	surface_tool.set_normal(normal)
	surface_tool.add_vertex(v0)

	surface_tool.set_normal(normal)
	surface_tool.add_vertex(v1)

	surface_tool.set_normal(normal)
	surface_tool.add_vertex(v2)


func _update_collision(arr_mesh: ArrayMesh) -> void:
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(arr_mesh.get_faces())
	_collision_shape.shape = shape
