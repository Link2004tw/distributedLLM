import subprocess
import time

workers = [
    (8001, 'worker-1'),
    (8002, 'worker-2'),
    (8003, 'worker-3'),
    (8004, 'worker-4'),
]

for port, wname in workers:
    cmd = ['.venv\\Scripts\\python.exe', '-c', 'import sys; sys.path.insert(0, "."); from workers.worker import app; import uvicorn; uvicorn.run(app, host="127.0.0.1", port=' + str(port) + ')']
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f'Started {wname} on port {port}, PID: {proc.pid}')
    time.sleep(0.5)

time.sleep(3)
print('Workers should be running')