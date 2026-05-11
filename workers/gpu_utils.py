import os
import subprocess
import sys


def check_gpu():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("=" * 60)
            print("GPU DETECTED")
            print("=" * 60)
            parts = result.stdout.strip().split(",")
            print(f"GPU: {parts[0]}")
            print(f"VRAM: {parts[1].strip()}")
            print("=" * 60)
            return True
        else:
            print("No GPU detected")
            return False
    except FileNotFoundError:
        print("nvidia-smi not found. No GPU available.")
        return False


def check_ollama():
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and "smollm2:135m" in result.stdout:
            print("\nOllama: Running with smollm2:135m model")
            return True
        else:
            print("Ollama not running or model not loaded")
            return False
    except Exception:
        print("Ollama not reachable")
        return False


def start_ollama():
    print("\nStarting Ollama server...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("Ollama started in background")
        return True
    except Exception as e:
        print(f"Failed to start Ollama: {e}")
        return False


def set_gpu_environment():
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["OLLAMA_GPU"] = "true"
    print("GPU environment variables set:")
    print("  CUDA_VISIBLE_DEVICES=0")
    print("  OLLAMA_GPU=true")


def get_gpu_memory():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            return f"VRAM: {parts[0].strip()} MB / {parts[1].strip()} MB"
    except Exception:
        pass
    return "VRAM: Unknown"


def get_gpu_info() -> dict:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            return {
                "gpu_utilization": int(parts[0]),
                "memory_used_mb": int(parts[1]),
                "memory_total_mb": int(parts[2]),
                "temperature_c": int(parts[3]),
                "power_watts": float(parts[4]) if len(parts) > 4 else 0.0
            }
    except Exception:
        pass
    return {"gpu_utilization": 0, "memory_used_mb": 0, "memory_total_mb": 6144, "temperature_c": 0, "power_watts": 0.0}


if __name__ == "__main__":
    print("=" * 60)
    print("GPU WORKER INITIALIZATION")
    print("=" * 60)

    gpu_available = check_gpu()
    ollama_running = check_ollama()

    if gpu_available and not ollama_running:
        start_ollama()

    if gpu_available:
        set_gpu_environment()

    print("\nGPU Memory:", get_gpu_memory())
    print("=" * 60)