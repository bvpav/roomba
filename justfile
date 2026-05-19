host := "roomba.local"
remote_dir := "~/firmware"

sync:
    rsync -avz firmware/ {{host}}:{{remote_dir}}/

teleop: sync
    ssh -X {{host}} "cd {{remote_dir}} && python3 teleop.py"
