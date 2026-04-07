extends CharacterBody3D

const SPEED := 3.0       # m/s
const TURN_SPEED := 2.0  # rad/s

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= gravity * delta

	var turn_input := Input.get_axis("ui_left", "ui_right")
	rotate_y(-turn_input * TURN_SPEED * delta)

	var throttle := Input.get_axis("ui_down", "ui_up")
	var forward := -transform.basis.z
	velocity.x = forward.x * throttle * SPEED
	velocity.z = forward.z * throttle * SPEED

	move_and_slide()
