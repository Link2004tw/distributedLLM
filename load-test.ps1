param(
    [int]$ConcurrentUsers = 50,
    [int]$RequestsPerUser = 5,
    [string]$Strategy = "capacity_aware"
)

$ErrorActionPreference = "Stop"

$LB_URL = "http://localhost:8000"

Write-Host "=== Concurrent Load Test ===" -ForegroundColor Cyan
Write-Host "Concurrent Users: $ConcurrentUsers"
Write-Host "Requests/User: $RequestsPerUser"
Write-Host "Strategy: $Strategy"
Write-Host ""

$client = New-Object System.Net.Http.HttpClient
$client.Timeout = New-Object System.TimeSpan(0, 5, 0)

$totalRequests = $ConcurrentUsers * $RequestsPerUser
$completedRequests = 0
$failedRequests = 0
$results = @()

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

$scriptBlock = {
    param($url, $count)
    $c = New-Object System.Net.Http.HttpClient
    $c.Timeout = New-Object System.TimeSpan(0, 5, 0)
    $success = 0
    $fail = 0
    $times = @()

    for ($i = 0; $i -lt $count; $i++) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            $body = @{
                query = "What is distributed computing?"
                top_k = 3
                user_id = "user-$([guid]::NewGuid().ToString().Substring(0,8))"
            } | ConvertTo-Json

            $content = New-Object System.Net.Http.StringContent($body, [System.Text.Encoding]::UTF8, "application/json")
            $resp = $c.PostAsync($url, $content).Result
            $sw.Stop()

            if ($resp.IsSuccessStatusCode) {
                $success++
                $times += $sw.ElapsedMilliseconds
            } else {
                $fail++
            }
        } catch {
            $fail++
        }
    }

    $c.Dispose()
    return @{
        Success = $success
        Fail = $fail
        Times = $times
    }
}

Write-Host "Starting $ConcurrentUsers concurrent users..." -ForegroundColor Yellow
$jobs = @()

for ($i = 0; $i -lt $ConcurrentUsers; $i++) {
    $job = Start-Job -ScriptBlock $scriptBlock -ArgumentList "$LB_URL/query", $RequestsPerUser
    $jobs += $job
}

foreach ($job in $jobs) {
    $result = Receive-Job -Job $job -Wait
    $completedRequests += $result.Success
    $failedRequests += $result.Fail
    $results += $result.Times
}

$stopwatch.Stop()

Remove-Job -Job $jobs -Force

Write-Host ""
Write-Host "=== Results ===" -ForegroundColor Green
Write-Host "Total Requests: $totalRequests"
Write-Host "Completed: $completedRequests"
Write-Host "Failed: $failedRequests"
Write-Host "Success Rate: $([math]::Round($completedRequests / $totalRequests * 100, 2))%"
Write-Host ""
Write-Host "Timing:" -ForegroundColor Yellow
Write-Host "Total Time: $([math]::Round($stopwatch.ElapsedMilliseconds / 1000, 2))s"
Write-Host "Avg Throughput: $([math]::Round($totalRequests / ($stopwatch.ElapsedMilliseconds / 1000), 2)) req/s"

if ($results.Count -gt 0) {
    $avg = ($results | Measure-Object -Average).Average
    $min = ($results | Measure-Object -Minimum).Minimum
    $max = ($results | Measure-Object -Maximum).Maximum
    $sorted = $results | Sort-Object
    $p95_idx = [int]($sorted.Count * 0.95)
    $p99_idx = [int]($sorted.Count * 0.99)
    $p95 = $sorted[$p95_idx]
    $p99 = $sorted[$p99_idx]

    Write-Host ""
    Write-Host "Latency (ms):" -ForegroundColor Yellow
    Write-Host "  Average: $([math]::Round($avg, 2))"
    Write-Host "  Min: $min"
    Write-Host "  Max: $max"
    Write-Host "  P95: $p95"
    Write-Host "  P99: $p99"
}

Write-Host ""
Write-Host "Worker Stats:" -ForegroundColor Yellow
try {
    $stats = Invoke-RestMethod -Uri "$LB_URL/workers" -TimeoutSec 5
    foreach ($w in $stats.workers) {
        $status = if ($w.healthy) { "[OK]" } else { "[DOWN]" }
        $color = if ($w.healthy) { "Green" } else { "Red" }
        Write-Host ("  {0} {1} - Conn: {2}, Latency: {3}ms" -f $status, $w.worker_id, $w.active_connections, $w.avg_latency_ms) -ForegroundColor $color
    }
} catch {
    Write-Host "  Could not fetch worker stats"
}

Write-Host ""
Write-Host "Load Balancer Stats:" -ForegroundColor Yellow
try {
    $lbStats = Invoke-RestMethod -Uri "$LB_URL/stats" -TimeoutSec 5 | ConvertTo-Json -Depth 3
    Write-Host $lbStats
} catch {
    Write-Host "  Could not fetch LB stats"
}
