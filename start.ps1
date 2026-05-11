# Start Ollama instances (6 total for distribution across workers)
# Using batch file wrapper to ensure environment variables are properly inherited

# Create temporary batch files to start Ollama with proper environment
$ollama_instances = @(
    @{port=11434; script="start-ollama-11434.bat"},
    @{port=11435; script="start-ollama-11435.bat"},
    @{port=11436; script="start-ollama-11436.bat"},
    @{port=11437; script="start-ollama-11437.bat"},
    @{port=11438; script="start-ollama-11438.bat"},
    @{port=11439; script="start-ollama-11439.bat"}
)

foreach ($instance in $ollama_instances) {
    $batch_content = "@echo off`nset OLLAMA_HOST=0.0.0.0:$($instance.port)`nollama serve"
    Set-Content -Path $instance.script -Value $batch_content -Force
    Start-Process $instance.script -NoNewWindow
}

Start-Sleep -Seconds 8

# Pull model (only needed once)
foreach ($port in @(11434, 11435, 11436, 11437, 11438, 11439)) {
    ollama -H localhost:$port pull smollm:135m 2>$null
}

Start-Sleep -Seconds 3

# Start 8 workers (scaled up from 3)
# Using hash tables for environment variables to ensure proper inheritance
$workers = @(
    @{id="worker-1"; port=8001; ollama_port=11434},
    @{id="worker-2"; port=8002; ollama_port=11435},
    @{id="worker-3"; port=8003; ollama_port=11436},
    @{id="worker-4"; port=8004; ollama_port=11437},
    @{id="worker-5"; port=8005; ollama_port=11438},
    @{id="worker-6"; port=8006; ollama_port=11439},
    @{id="worker-7"; port=8007; ollama_port=11434},
    @{id="worker-8"; port=8008; ollama_port=11435}
)

foreach ($worker in $workers) {
    $env_vars = @{
        WORKER_ID = $worker.id
        PORT = $worker.port
        OLLAMA_URL = "http://localhost:$($worker.ollama_port)"
        MAX_CONCURRENT_TASKS = "20"
        BACKPRESSURE_QUEUE_SIZE = "200"
    }
    
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "uvicorn"
    $pinfo.Arguments = "workers.worker:app --port $($worker.port) --log-level warning"
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true
    
    # Copy environment variables
    foreach ($key in $env_vars.Keys) {
        $pinfo.EnvironmentVariables[$key] = $env_vars[$key]
    }
    
    $proc = [System.Diagnostics.Process]::Start($pinfo)
    Start-Sleep -Milliseconds 500
}

Start-Sleep -Seconds 3

Write-Host "All 8 workers started with scaled capacity. Total capacity: ~160 concurrent requests (20 tasks × 8 workers)"
