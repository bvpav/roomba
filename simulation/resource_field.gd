@tool
extends MeshInstance3D

## Procedural terrain for the 400×200 cm resource field, plus boundary strips,
## penalty field, and penalty walls on three edges (top, right, bottom).
## The left edge is open to connect with the base field in the parent scene.
## Runs in-editor (@tool) and at runtime.


# ── Playing field ────────────────────────────────────────────────────────────
const FIELD_WIDTH := 4.0    # 400 cm (local X axis)
const FIELD_DEPTH := 2.0    # 200 cm (local Z axis)
const CELLS_X := 16
const CELLS_Z := 8
const NOISE_SEED := 12345
const MAX_SLOPE_TAN := 0.57735  # tan(30°)

# ── Surrounding geometry ─────────────────────────────────────────────────────
const BOUNDARY_WIDTH := 0.05    # 5 cm
const PENALTY_WIDTH := 0.10     # 10 cm
const WALL_HEIGHT := 0.25       # 25 cm above terrain surface
const WALL_THICKNESS := 0.25    # 25 cm


@export var material_field: Material
@export var material_boundary: Material
@export var material_penalty: Material


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
	var half_w := FIELD_WIDTH * 0.5
	var half_d := FIELD_DEPTH * 0.5

	var h := _generate_heightmap(cell_w, cell_d, max_dy_x, max_dy_z)

	# ── Perimeter heights at the two right corners ───────────────────
	var h_top_right: float = h[0][CELLS_X]
	var h_bottom_right: float = h[CELLS_Z][CELLS_X]

	# ── Edge vertices (ordered so along × outward points up) ─────────
	var top_edge: Array[Vector3] = []
	for ii in range(CELLS_X + 1):
		top_edge.append(Vector3(-half_w + ii * cell_w, h[0][ii], -half_d))

	var right_edge: Array[Vector3] = []
	for jj in range(CELLS_Z + 1):
		right_edge.append(Vector3(half_w, h[jj][CELLS_X], -half_d + jj * cell_d))

	var bottom_edge: Array[Vector3] = []
	for ii in range(CELLS_X, -1, -1):
		bottom_edge.append(Vector3(-half_w + ii * cell_w, h[CELLS_Z][ii], half_d))

	# ── Build all surfaces ───────────────────────────────────────────
	var arr_mesh := ArrayMesh.new()
	_build_field_surface(arr_mesh, h, cell_w, cell_d)
	_build_boundary_surface(arr_mesh, top_edge, right_edge, bottom_edge,
		h_top_right, h_bottom_right, half_w, half_d)
	_build_penalty_surface(arr_mesh, top_edge, right_edge, bottom_edge,
		h_top_right, h_bottom_right, half_w, half_d)

	# ── Assign materials ─────────────────────────────────────────────
	if material_field:
		arr_mesh.surface_set_material(0, material_field)
	if material_boundary:
		arr_mesh.surface_set_material(1, material_boundary)
	if material_penalty:
		arr_mesh.surface_set_material(2, material_penalty)

	mesh = arr_mesh
	_update_collision(arr_mesh)


# ── Heightmap ────────────────────────────────────────────────────────────────


func _generate_heightmap(
	cell_w: float, cell_d: float,
	max_dy_x: float, max_dy_z: float,
) -> Array[Array]:
	var noise := FastNoiseLite.new()
	noise.seed = NOISE_SEED
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.35

	# Accumulate noise-driven slopes from the base-field edge (ii=0).
	var h: Array[Array] = []
	for jj in range(CELLS_Z + 1):
		var row: Array[float] = []
		row.append(0.0)
		for ii in range(1, CELLS_X + 1):
			var nx := -FIELD_WIDTH * 0.5 + ii * cell_w
			var nz := -FIELD_DEPTH * 0.5 + jj * cell_d
			var slope := noise.get_noise_2d(nx, nz) * max_dy_x
			row.append(row[ii - 1] + slope)
		h.append(row)

	# Shift minimum to 0.
	var min_h: float = h[0][0]
	for jj in range(CELLS_Z + 1):
		for ii in range(CELLS_X + 1):
			if h[jj][ii] < min_h:
				min_h = h[jj][ii]
	for jj in range(CELLS_Z + 1):
		for ii in range(CELLS_X + 1):
			h[jj][ii] -= min_h

	# Iterative relaxation — enforce 30° slope in both axes.
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

	return h


# ── Surface 0: playing field terrain ─────────────────────────────────────────


func _build_field_surface(
	arr_mesh: ArrayMesh, h: Array[Array],
	cell_w: float, cell_d: float,
) -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

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

			if jj % 2 != 0:
				_add_tri(st, v00, v10, v11)
				_add_tri(st, v00, v11, v01)
			else:
				_add_tri(st, v00, v10, v01)
				_add_tri(st, v10, v11, v01)

	st.commit(arr_mesh)


# ── Surface 1: boundary strips ───────────────────────────────────────────────


func _build_boundary_surface(
	arr_mesh: ArrayMesh,
	top_edge: Array[Vector3], right_edge: Array[Vector3],
	bottom_edge: Array[Vector3],
	h_top_right: float, h_bottom_right: float,
	half_w: float, half_d: float,
) -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var bw := BOUNDARY_WIDTH

	# Three straight edge strips
	_build_strip(st, top_edge, Vector3(0.0, 0.0, -1.0), bw)
	_build_strip(st, right_edge, Vector3(1.0, 0.0, 0.0), bw)
	_build_strip(st, bottom_edge, Vector3(0.0, 0.0, 1.0), bw)

	# Top-right corner patch (flat quad at h_top_right)
	var tr_inner := Vector3(half_w, h_top_right, -half_d)
	var tr_top := Vector3(half_w, h_top_right, -half_d - bw)
	var tr_corner := Vector3(half_w + bw, h_top_right, -half_d - bw)
	var tr_right := Vector3(half_w + bw, h_top_right, -half_d)
	_add_quad(st, tr_inner, tr_top, tr_corner, tr_right, Vector3.UP)

	# Bottom-right corner patch (flat quad at h_bottom_right)
	var br_inner := Vector3(half_w, h_bottom_right, half_d)
	var br_bottom := Vector3(half_w, h_bottom_right, half_d + bw)
	var br_corner := Vector3(half_w + bw, h_bottom_right, half_d + bw)
	var br_right := Vector3(half_w + bw, h_bottom_right, half_d)
	_add_quad(st, br_inner, br_right, br_corner, br_bottom, Vector3.UP)

	st.commit(arr_mesh)


# ── Surface 2: penalty field + penalty wall ──────────────────────────────────


func _build_penalty_surface(
	arr_mesh: ArrayMesh,
	top_edge: Array[Vector3], right_edge: Array[Vector3],
	bottom_edge: Array[Vector3],
	h_top_right: float, h_bottom_right: float,
	half_w: float, half_d: float,
) -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var bw := BOUNDARY_WIDTH
	var pw := PENALTY_WIDTH

	# ── Compute boundary outer vertices (= penalty inner) ───────────
	var top_boundary_outer := _offset_vertices(top_edge, Vector3(0.0, 0.0, -1.0), bw)
	var right_boundary_outer := _offset_vertices(right_edge, Vector3(1.0, 0.0, 0.0), bw)
	var bottom_boundary_outer := _offset_vertices(bottom_edge, Vector3(0.0, 0.0, 1.0), bw)

	# Boundary corner positions
	var tr_boundary_corner := Vector3(half_w + bw, h_top_right, -half_d - bw)
	var br_boundary_corner := Vector3(half_w + bw, h_bottom_right, half_d + bw)

	# ── Extended penalty inner lists (include corner vertices) ───────
	# Top: straight + TR boundary corner
	var top_penalty_inner: Array[Vector3] = []
	top_penalty_inner.append_array(top_boundary_outer)
	top_penalty_inner.append(tr_boundary_corner)

	# Right: TR boundary corner + straight + BR boundary corner
	var right_penalty_inner: Array[Vector3] = []
	right_penalty_inner.append(tr_boundary_corner)
	right_penalty_inner.append_array(right_boundary_outer)
	right_penalty_inner.append(br_boundary_corner)

	# Bottom: BR boundary corner + straight
	var bottom_penalty_inner: Array[Vector3] = []
	bottom_penalty_inner.append(br_boundary_corner)
	bottom_penalty_inner.append_array(bottom_boundary_outer)

	# ── Penalty strips ───────────────────────────────────────────────
	_build_strip(st, top_penalty_inner, Vector3(0.0, 0.0, -1.0), pw)
	_build_strip(st, right_penalty_inner, Vector3(1.0, 0.0, 0.0), pw)
	_build_strip(st, bottom_penalty_inner, Vector3(0.0, 0.0, 1.0), pw)

	# ── Penalty corner quads (PW × PW patches at each corner) ───────
	# Top-right
	var tr_pen_corner := tr_boundary_corner
	_add_quad(st,
		tr_pen_corner,
		tr_pen_corner + Vector3(0.0, 0.0, -pw),
		tr_pen_corner + Vector3(pw, 0.0, -pw),
		tr_pen_corner + Vector3(pw, 0.0, 0.0),
		Vector3.UP)

	# Bottom-right
	var br_pen_corner := br_boundary_corner
	_add_quad(st,
		br_pen_corner,
		br_pen_corner + Vector3(pw, 0.0, 0.0),
		br_pen_corner + Vector3(pw, 0.0, pw),
		br_pen_corner + Vector3(0.0, 0.0, pw),
		Vector3.UP)

	# ── Penalty outer vertices (wall base positions) ─────────────────
	var top_penalty_outer := _offset_vertices(top_penalty_inner, Vector3(0.0, 0.0, -1.0), pw)
	var right_penalty_outer := _offset_vertices(right_penalty_inner, Vector3(1.0, 0.0, 0.0), pw)
	var bottom_penalty_outer := _offset_vertices(bottom_penalty_inner, Vector3(0.0, 0.0, 1.0), pw)

	# Penalty outer corner positions (miter points)
	var tr_penalty_corner := Vector3(half_w + bw + pw, h_top_right, -half_d - bw - pw)
	var br_penalty_corner := Vector3(half_w + bw + pw, h_bottom_right, half_d + bw + pw)

	# ── Penalty walls ────────────────────────────────────────────────
	# Extend wall vertex lists to include corner miter points
	var top_wall_vertices: Array[Vector3] = []
	top_wall_vertices.append_array(top_penalty_outer)
	top_wall_vertices.append(tr_penalty_corner)

	var right_wall_vertices: Array[Vector3] = []
	right_wall_vertices.append(tr_penalty_corner)
	right_wall_vertices.append_array(right_penalty_outer)
	right_wall_vertices.append(br_penalty_corner)

	var bottom_wall_vertices: Array[Vector3] = []
	bottom_wall_vertices.append(br_penalty_corner)
	bottom_wall_vertices.append_array(bottom_penalty_outer)

	_build_wall(st, top_wall_vertices, Vector3(0.0, 0.0, -1.0))
	_build_wall(st, right_wall_vertices, Vector3(1.0, 0.0, 0.0))
	_build_wall(st, bottom_wall_vertices, Vector3(0.0, 0.0, 1.0))

	# Wall corner blocks (overlapping with adjacent walls is acceptable)
	_build_wall_corner(st, tr_penalty_corner,
		Vector3(0.0, 0.0, -1.0), Vector3(1.0, 0.0, 0.0))
	_build_wall_corner(st, br_penalty_corner,
		Vector3(0.0, 0.0, 1.0), Vector3(1.0, 0.0, 0.0))

	st.commit(arr_mesh)


# ── Strip / wall builder helpers ─────────────────────────────────────────────


## Builds a horizontal strip of quads along ordered perimeter vertices.
## Each outer vertex is offset by [outward * width] at the same Y height.
## Vertex order must satisfy: (along_direction × outward).y > 0.
func _build_strip(
	st: SurfaceTool,
	inner_vertices: Array[Vector3],
	outward: Vector3,
	width: float,
) -> void:
	for ii in range(inner_vertices.size() - 1):
		var a_inner := inner_vertices[ii]
		var b_inner := inner_vertices[ii + 1]
		var a_outer := a_inner + outward * width
		var b_outer := b_inner + outward * width
		_add_tri(st, a_inner, a_outer, b_outer)
		_add_tri(st, a_inner, b_outer, b_inner)


## Builds a wall with box cross-section along ordered penalty-outer vertices.
## Wall goes from Y=0 to Y=(vertex.y + WALL_HEIGHT), extending outward by
## WALL_THICKNESS. The top face slopes only along the edge direction.
func _build_wall(
	st: SurfaceTool,
	vertices: Array[Vector3],
	outward: Vector3,
) -> void:
	var wall_offset := outward * WALL_THICKNESS

	for ii in range(vertices.size() - 1):
		var a := vertices[ii]
		var b := vertices[ii + 1]

		# Wall top is WALL_HEIGHT above the terrain surface at each vertex.
		# Inner and outer top share the same Y so the top face only slopes
		# along the edge direction.
		var a_top_y := a.y + WALL_HEIGHT
		var b_top_y := b.y + WALL_HEIGHT

		var a_ib := Vector3(a.x, 0.0, a.z)
		var b_ib := Vector3(b.x, 0.0, b.z)
		var a_it := Vector3(a.x, a_top_y, a.z)
		var b_it := Vector3(b.x, b_top_y, b.z)
		var a_ob := a_ib + wall_offset
		var b_ob := b_ib + wall_offset
		var a_ot := Vector3(a_it.x + wall_offset.x, a_top_y, a_it.z + wall_offset.z)
		var b_ot := Vector3(b_it.x + wall_offset.x, b_top_y, b_it.z + wall_offset.z)

		# Inner face (normal points inward, toward field)
		_add_quad(st, a_ib, a_it, b_it, b_ib, -outward)
		# Outer face (normal points outward)
		_add_quad(st, a_ob, b_ob, b_ot, a_ot, outward)
		# Top cap (normal points up)
		_add_quad(st, a_it, a_ot, b_ot, b_it, Vector3.UP)


## Builds a solid wall corner block where two walls meet at 90°.
func _build_wall_corner(
	st: SurfaceTool,
	corner_pos: Vector3,
	dir_a: Vector3,
	dir_b: Vector3,
) -> void:
	var oa := dir_a * WALL_THICKNESS
	var ob := dir_b * WALL_THICKNESS
	var top_y := corner_pos.y + WALL_HEIGHT

	var base := Vector3(corner_pos.x, 0.0, corner_pos.z)
	var b00 := base
	var b10 := base + ob
	var b01 := base + oa
	var b11 := base + oa + ob
	var t00 := Vector3(b00.x, top_y, b00.z)
	var t10 := Vector3(b10.x, top_y, b10.z)
	var t01 := Vector3(b01.x, top_y, b01.z)
	var t11 := Vector3(b11.x, top_y, b11.z)

	# Outer face in dir_a direction
	_add_quad(st, b01, t01, t11, b11, dir_a)
	# Outer face in dir_b direction
	_add_quad(st, b10, b11, t11, t10, dir_b)
	# Top cap
	_add_quad(st, t00, t01, t11, t10, Vector3.UP)
	# Inner face opposite dir_a (closing the box toward the field)
	_add_quad(st, b00, b10, t10, t00, -dir_a)
	# Inner face opposite dir_b
	_add_quad(st, b00, t00, t01, b01, -dir_b)


# ── Geometry helpers ─────────────────────────────────────────────────────────


## Returns a copy of vertices offset by [direction * distance], keeping Y.
func _offset_vertices(
	vertices: Array[Vector3],
	direction: Vector3,
	distance: float,
) -> Array[Vector3]:
	var result: Array[Vector3] = []
	var offset := direction * distance
	for v in vertices:
		result.append(v + offset)
	return result


## Adds a triangle with a shared per-face normal (flat / faceted shading).
func _add_tri(
	st: SurfaceTool,
	v0: Vector3, v1: Vector3, v2: Vector3,
) -> void:
	var normal := (v2 - v0).cross(v1 - v0).normalized()
	st.set_normal(normal)
	st.add_vertex(v0)
	st.set_normal(normal)
	st.add_vertex(v1)
	st.set_normal(normal)
	st.add_vertex(v2)


## Adds a quad (two triangles) with auto-corrected winding.
## Vertices must be in sequential order around the quad perimeter.
## [normal_hint] determines which direction the face should point.
func _add_quad(
	st: SurfaceTool,
	v0: Vector3, v1: Vector3, v2: Vector3, v3: Vector3,
	normal_hint: Vector3,
) -> void:
	var test_normal := (v2 - v0).cross(v1 - v0)
	if test_normal.dot(normal_hint) >= 0.0:
		_add_tri(st, v0, v1, v2)
		_add_tri(st, v0, v2, v3)
	else:
		_add_tri(st, v0, v2, v1)
		_add_tri(st, v0, v3, v2)


func _update_collision(arr_mesh: ArrayMesh) -> void:
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(arr_mesh.get_faces())
	_collision_shape.shape = shape
