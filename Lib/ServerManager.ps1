# ServerManager.ps1
# Handles starting/stopping llama-server, reading output, polling metrics

$Script:ServerProcess = $null
$Script:ServerStartTime = $null
$Script:MetricsTimer = $null
$Script:ResourceTimer = $null
$Script:UptimeTimer = $null
$Script:LastMetrics = @{}
$Script:TotalTokensAllTime = 0
$Script:RequestsAllTime = 0
$Script:OutputCallback = $null
$Script:StatusCallback = $null

function Start-LlamaServer {
    param(
        [string]$ExePath,
        [hashtable]$ServerArgs,
        [scriptblock]$OnOutput,
        [scriptblock]$OnStatus
    )

    if ($Script:ServerProcess -and -not $Script:ServerProcess.HasExited) {
        return @{ Success = $false; Error = "Server is already running" }
    }

    $Script:OutputCallback = $OnOutput
    $Script:StatusCallback = $OnStatus

    if ([string]::IsNullOrWhiteSpace($ExePath)) {
        return @{ Success = $false; Error = "Executable path is empty. Set runtime path or place llama-server.exe next to D:\Release." }
    }

    if (-not (Test-Path $ExePath -PathType Leaf)) {
        return @{ Success = $false; Error = "Executable not found: $ExePath" }
    }

    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $ExePath
        $psi.Arguments = ConvertTo-ServerArgumentString -ServerArgs $ServerArgs
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

        $Script:ServerProcess = New-Object System.Diagnostics.Process
        $Script:ServerProcess.StartInfo = $psi
        $Script:ServerProcess.EnableRaisingEvents = $true

        $Script:ServerProcess.add_OutputDataReceived({
            param($sender, $eventArgs)
            $line = $eventArgs.Data
            if ($line) {
                $timestamp = Get-Date -Format "HH:mm:ss"
                $colored = ColorizeLogLine -Line $line
                if ($Script:OutputCallback) {
                    & $Script:OutputCallback "$timestamp  $colored"
                }
                # Parse metrics from output if present
                ParseMetricsOutput -Line $line
            }
        })

        $Script:ServerProcess.add_ErrorDataReceived({
            param($sender, $eventArgs)
            $line = $eventArgs.Data
            if ($line) {
                $timestamp = Get-Date -Format "HH:mm:ss"
                if ($Script:OutputCallback) {
                    & $Script:OutputCallback "$timestamp  [ERROR] $line"
                }
            }
        })

        $Script:ServerProcess.add_Exited({
            param($sender, $eventArgs)
            try {
                $code = $sender.ExitCode
                if ($Script:OutputCallback) {
                    & $Script:OutputCallback "[INFO] llama-server exited with code $code"
                }
                if ($Script:StatusCallback) {
                    & $Script:StatusCallback "exited" @{ ExitCode = $code }
                }
            } catch { }
        })

        $Script:ServerProcess.Start() | Out-Null
        $Script:ServerProcess.BeginOutputReadLine()
        $Script:ServerProcess.BeginErrorReadLine()
        $Script:ServerStartTime = Get-Date

        # Start timers
        Start-MetricsTimer -Port $ServerArgs["port"]
        Start-ResourceTimer
        Start-UptimeTimer

        return @{ Success = $true; ProcessId = $Script:ServerProcess.Id }
    } catch {
        $message = $_.Exception.Message
        if (-not $message) { $message = $_.ToString() }
        return @{ Success = $false; Error = $message; Detail = $_.ScriptStackTrace }
    }
}

function Stop-LlamaServer {
    if (-not $Script:ServerProcess -or $Script:ServerProcess.HasExited) {
        return @{ Success = $true }
    }

    try {
        # Try graceful shutdown via API first
        $port = "1234"
        if ($Script:LastMetrics.ContainsKey("port")) {
            $port = $Script:LastMetrics["port"]
        }

        # Send shutdown signal if supported
        try {
            $uri = "http://127.0.0.1:$port/health"
            $response = Invoke-WebRequest -Uri $uri -Method Post -TimeoutSec 2 -ErrorAction SilentlyContinue
        } catch { }

        # Kill the process
        $Script:ServerProcess.Kill()
        $Script:ServerProcess.WaitForExit(3000)
        $Script:ServerProcess.Dispose()
    } catch {
        try { $Script:ServerProcess.Kill() } catch { }
    } finally {
        $Script:ServerProcess = $null
        $Script:ServerStartTime = $null
        Stop-MetricsTimer
        Stop-ResourceTimer
        Stop-UptimeTimer
    }

    return @{ Success = $true }
}

function Get-ServerStatus {
    if (-not $Script:ServerProcess) { return "stopped" }
    if ($Script:ServerProcess.HasExited) { return "stopped" }
    return "running"
}

function Get-ServerUptime {
    if (-not $Script:ServerStartTime) { return "--" }
    $elapsed = (Get-Date) - $Script:ServerStartTime
    if ($elapsed.TotalHours -ge 1) {
        return "{0}h {1}m {2}s" -f $elapsed.Hours, $elapsed.Minutes, $elapsed.Seconds
    }
    return "{0}m {1}s" -f $elapsed.Minutes, $elapsed.Seconds
}

function Start-MetricsTimer {
    param([string]$Port = "1234")

    # Poll llama-server metrics endpoint every 2 seconds
    $callback = [System.Threading.TimerCallback]{
        param($state)
        Update-ServerMetrics -Port $state
    }
    $Script:MetricsTimer = [System.Threading.Timer]::new($callback, $Port, 2000, 2000)
}

function Stop-MetricsTimer {
    if ($Script:MetricsTimer) {
        $Script:MetricsTimer.Dispose()
        $Script:MetricsTimer = $null
    }
}

function Update-ServerMetrics {
    param([string]$Port = "1234")

    try {
        $uri = "http://127.0.0.1:$Port/metrics"
        $response = Invoke-WebRequest -Uri $uri -TimeoutSec 2 -ErrorAction SilentlyContinue

        if ($response) {
            $content = $response.Content
            $metrics = ParsePrometheusMetrics -Content $content
            $Script:LastMetrics = $metrics
            $Script:LastMetrics["port"] = $Port

            if ($Script:StatusCallback) {
                & $Script:StatusCallback "metrics" $metrics
            }
        }
    } catch {
        # Server may not have metrics endpoint or not ready yet
    }
}

function ParsePrometheusMetrics {
    param([string]$Content)

    $metrics = @{}

    # llama_server_request_success_total
    if ($Content -match 'llama_server_request_success_total\s+(\d+)') {
        $metrics["requests"] = [int]$Matches[1]
    }

    # prompt_eval_n (total prompt evaluations)
    if ($Content -match 'prompt_eval_n_total\s+(\d+)') {
        $metrics["total_prompt_tokens"] = [int]$Matches[1]
    }

    # eval_n (total decode tokens)
    if ($Content -match 'eval_n_total\s+(\d+)') {
        $metrics["total_decode_tokens"] = [int]$Matches[1]
    }

    # prompt_eval_seconds (total time for prompt eval)
    if ($Content -match 'prompt_eval_seconds_total\s+([\d.]+)') {
        $metrics["total_prompt_time"] = [double]$Matches[1]
    }

    # eval_seconds (total time for decoding)
    if ($Content -match 'eval_seconds_total\s+([\d.]+)') {
        $metrics["total_decode_time"] = [double]$Matches[1]
    }

    # prompt_eval_tokens_per_second
    if ($Content -match 'prompt_eval_tokens_per_second\s+([\d.]+)') {
        $metrics["peps"] = [double]$Matches[1]
    }

    # tokens_per_second
    if ($Content -match 'tokens_per_second\s+([\d.]+)') {
        $metrics["tps"] = [double]$Matches[1]
    }

    # kv_cache_usage_count (KV cache utilization)
    if ($Content -match 'kv_cache_usage_count\s+([\d.]+)') {
        $metrics["kv_usage"] = [double]$Matches[1]
    }

    # context_len
    if ($Content -match 'n_ctx\s+(\d+)') {
        $metrics["ctx_size"] = [int]$Matches[1]
    }

    return $metrics
}

function ParseMetricsOutput {
    param([string]$Line)

    # Also try to parse metrics from stderr output
    if ($Line -match 'prompt_eval_count.*?(\d+)') {
        $Script:LastMetrics["prompt_eval_count"] = [int]$Matches[1]
    }
    if ($Line -match 'eval_count.*?(\d+)') {
        $Script:LastMetrics["eval_count"] = [int]$Matches[1]
    }
    if ($Line -match '(\d+)\s*tokens/sec') {
        $Script:LastMetrics["tps"] = [double]$Matches[1]
    }
}

function Start-ResourceTimer {
    # Update system resource metrics every 3 seconds
    $callback = [System.Threading.TimerCallback]{
        param($state)
        Update-SystemResources
    }
    $Script:ResourceTimer = [System.Threading.Timer]::new($callback, $null, 1000, 3000)
}

function Stop-ResourceTimer {
    if ($Script:ResourceTimer) {
        $Script:ResourceTimer.Dispose()
        $Script:ResourceTimer = $null
    }
}

function Start-UptimeTimer {
    # Placeholder for future uptime push updates; uptime is read on demand by the UI/status code.
}

function Stop-UptimeTimer {
    if ($Script:UptimeTimer) {
        $Script:UptimeTimer.Dispose()
        $Script:UptimeTimer = $null
    }
}

function Update-SystemResources {
    try {
        # CPU usage
        $cpuUsage = Get-CpuUsage

        # RAM usage
        $ramInfo = Get-RamUsage

        # GPU info (if NVIDIA)
        $gpuInfo = Get-GpuInfo

        if ($Script:StatusCallback) {
            & $Script:StatusCallback "resources" @{
                Cpu = $cpuUsage
                Ram = $ramInfo
                Gpu = $gpuInfo
            }
        }
    } catch {
        # Silently fail - resources may not be available
    }
}

function Get-CpuUsage {
    try {
        $totalWork = 0
        $cpuCount = (Get-CimInstance Win32_Processor).Count
        foreach ($cpu in Get-CimInstance Win32_Processor) {
            $totalWork += $cpu.LoadPercentage
        }
        return [math]::Round($totalWork / $cpuCount, 1)
    } catch {
        return 0
    }
}

function Get-RamUsage {
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
        $freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
        $usedGB = $totalGB - $freeGB
        return @{
            TotalGB = $totalGB
            UsedGB = [math]::Round($usedGB, 1)
            FreeGB = $freeGB
            Percent = [math]::Round(($usedGB / $totalGB) * 100, 1)
        }
    } catch {
        return @{ TotalGB = 0; UsedGB = 0; FreeGB = 0; Percent = 0 }
    }
}

function Get-GpuInfo {
    try {
        # Try NVIDIA WMI extension first
        $nvidiaGpu = Get-CimInstance -Namespace "ROOT\nvvd" -ClassName "NVDIA_GPU" -ErrorAction SilentlyContinue
        if ($nvidiaGpu) {
            $util = 0
            $usedVram = 0
            $totalVram = 0
            foreach ($gpu in $nvidiaGpu) {
                $util += [int]$gpu.PercentageGpuUtilization
                $usedVram += [math]::Round($gpu.MemoryUsedGB, 1)
                $totalVram += [math]::Round($gpu.MemoryTotalGB, 1)
            }
            return @{
                Utilization = [math]::Round($util / $nvidiaGpu.Count, 1)
                UsedVramGB = $usedVram
                TotalVramGB = $totalVram
                Driver = "NVIDIA"
            }
        }

        # Fallback: try Get-NvidiaStats or other methods
        # Check for nvidia-smi
        $ssmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
        if ($ssmi) {
            $output = nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>$null
            if ($output) {
                $parts = $output -split ','
                return @{
                    Utilization = [double]$parts[0].Trim()
                    UsedVramGB = [math]::Round([double]$parts[1].Trim() / 1024, 1)
                    TotalVramGB = [math]::Round([double]$parts[2].Trim() / 1024, 1)
                    Driver = "NVIDIA"
                }
            }
        }

        return $null
    } catch {
        return $null
    }
}

function ColorizeLogLine {
    param([string]$Line)

    $line = $Line.Trim()
    if ($line -match '^\[.*?\].*?error' -or $line -match '^\[.*?\].*?ERROR') {
        return "`e[31m$line`e[0m"
    }
    if ($line -match '^\[.*?\].*?warning' -or $line -match '^\[.*?\].*?WARN') {
        return "`e[33m$line`e[0m"
    }
    if ($line -match '^\[.*?\].*?starting' -or $line -match '^\[.*?\].*?loaded') {
        return "`e[32m$line`e[0m"
    }
    return $line
}

function Build-CommandArgs {
    param(
        [string]$ModelPath,
        [hashtable]$Settings
    )

    $serverArgs = @{}

    # Model
    $serverArgs["model"] = $ModelPath

    # GPU
    $serverArgs["n-gpu-layers"] = $Settings.GpuLayers
    if ($Settings.NcpuMoe -and [int]$Settings.NcpuMoe -gt 0) {
        $serverArgs["n-cpu-moe"] = $Settings.NcpuMoe
        $serverArgs["cpu-moe"] = $true
    }

    # Context & batching
    $serverArgs["ctx-size"] = $Settings.CtxSize
    $serverArgs["batch-size"] = $Settings.BatchSize
    $serverArgs["ubatch-size"] = $Settings.UBatchSize

    # Threads
    $serverArgs["threads"] = $Settings.Threads

    # TurboQuant
    if ($Settings.CacheTypeK) { $serverArgs["cache-type-k"] = $Settings.CacheTypeK }
    if ($Settings.CacheTypeV) { $serverArgs["cache-type-v"] = $Settings.CacheTypeV }

    # Flash attention
    if ($Settings.FlashAttn) { $serverArgs["flash-attn"] = $true }

    # Split mode
    if ($Settings.SplitMode -and $Settings.SplitMode -ne "auto") {
        $serverArgs["split-mode"] = $Settings.SplitMode
    }
    if ($Settings.TensorSplit -and [double]$Settings.TensorSplit -gt 0) {
        $serverArgs["tensor-split"] = $Settings.TensorSplit
    }

    # Mlock / No mmap
    if ($Settings.Mlock) { $serverArgs["mlock"] = $true }
    if ($Settings.NoMmap) { $serverArgs["no-mmap"] = $true }

    # Chat / Jinja
    if ($Settings.Jinja) { $serverArgs["jinja"] = $true }

    # Reasoning
    if ($Settings.Thinking) {
        if ($Settings.ReasoningFormat -eq "force") {
            $serverArgs["reasoning-format"] = "force"
        } elseif ($Settings.ReasoningFormat -eq "none") {
            $serverArgs["reasoning-format"] = "none"
        }
    } else {
        $serverArgs["reasoning-format"] = "none"
    }
    if ($Settings.ReasoningBudget) {
        $serverArgs["reasoning-budget"] = $Settings.ReasoningBudget
    }

    # Sampling
    if ($Settings.Temp) { $serverArgs["temp"] = $Settings.Temp }
    if ($Settings.TopP) { $serverArgs["top-p"] = $Settings.TopP }
    if ($Settings.TopK) { $serverArgs["top-k"] = $Settings.TopK }
    if ($Settings.MinP) { $serverArgs["min-p"] = $Settings.MinP }
    if ($Settings.TypicalP -and [double]$Settings.TypicalP -ne 1.0) { $serverArgs["typical-p"] = $Settings.TypicalP }
    if ($Settings.RepeatPenalty) { $serverArgs["repeat-penalty"] = $Settings.RepeatPenalty }
    if ($Settings.RepeatLastN) { $serverArgs["repeat-last-n"] = $Settings.RepeatLastN }
    if ($Settings.PresencePenalty) { $serverArgs["presence-penalty"] = $Settings.PresencePenalty }
    if ($Settings.FreqPenalty) { $serverArgs["frequency-penalty"] = $Settings.FreqPenalty }
    if ($Settings.Seed -and [int]$Settings.Seed -ge 0) { $serverArgs["seed"] = $Settings.Seed }

    # DRY
    if ($Settings.DryMultiplier -and [double]$Settings.DryMultiplier -gt 0) {
        $serverArgs["dry-multiplier"] = $Settings.DryMultiplier
        $serverArgs["dry-base"] = $Settings.DryBase
        $serverArgs["dry-allowed-length"] = $Settings.DryAllowed
        $serverArgs["dry-penalty-last-n"] = -1
    }

    # XTC
    if ($Settings.XtcProb -and [double]$Settings.XtcProb -gt 0) {
        $serverArgs["xtc-probability"] = $Settings.XtcProb
        $serverArgs["xtc-threshold"] = $Settings.XtcThresh
    }

    # Server
    $serverArgs["host"] = $Settings.Host
    $serverArgs["port"] = $Settings.Port
    if ($Settings.Parallel -and [int]$Settings.Parallel -gt 1) { $serverArgs["parallel"] = $Settings.Parallel }
    if ($Settings.Alias) { $serverArgs["alias"] = $Settings.Alias }
    if ($Settings.ApiKey) { $serverArgs["api-key"] = $Settings.ApiKey }

    # Features
    if (-not $Settings.Webui) { $serverArgs["no-webui"] = $true }
    if ($Settings.Metrics) { $serverArgs["metrics"] = $true }
    if ($Settings.ContBatching) { $serverArgs["cont-batching"] = $true }

    return $serverArgs
}

function Get-CommandString {
    param(
        [string]$ExePath,
        [hashtable]$ServerArgs
    )

    $cmd = "`"$ExePath`""
    foreach ($key in $ServerArgs.Keys) {
        $val = $ServerArgs[$key]
        if ($val -is [bool] -and $val -eq $true) {
            $cmd += " --$key"
        } elseif (-not ($val -is [bool]) -and $val -ne $null -and $val -ne "") {
            $cmd += " --$key `"$val`""
        }
    }
    return $cmd
}

function ConvertTo-ServerArgumentString {
    param([hashtable]$ServerArgs)

    $parts = @()
    foreach ($key in $ServerArgs.Keys) {
        $val = $ServerArgs[$key]
        if ($val -is [bool] -and $val -eq $true) {
            $parts += "--$key"
        } elseif (-not ($val -is [bool]) -and $val -ne $null -and $val -ne "") {
            $escaped = ([string]$val) -replace '"', '\"'
            $parts += "--$key `"$escaped`""
        }
    }
    return ($parts -join " ")
}
