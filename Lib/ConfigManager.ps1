# ConfigManager.ps1
# Handles presets, model registry, session persistence, and runtime path

$Script:ConfigDir = Join-Path $PSScriptRoot ".."
$Script:PresetsDir = Join-Path $Script:ConfigDir "presets"
$Script:ModelConfigsDir = Join-Path $Script:ConfigDir "model-configs"
$Script:SessionDir = Join-Path $env:APPDATA "TurboLauncher"
$Script:SessionFile = Join-Path $Script:SessionDir "session.json"
$Script:RegistryFile = Join-Path $Script:ConfigDir "models.registry"
$Script:RuntimePathFile = Join-Path $Script:SessionDir "runtime_path.txt"

# Ensure directories exist
New-Item -ItemType Directory -Force -Path $Script:PresetsDir | Out-Null
New-Item -ItemType Directory -Force -Path $Script:ModelConfigsDir | Out-Null
New-Item -ItemType Directory -Force -Path $Script:SessionDir | Out-Null

# Built-in presets
$Script:BuiltInPresets = @(
    @{ Name = "Agentic AI"; Description = "Thinking ON + preserve, optimized for tool calling and MCP agents"; File = "agentic-ai.json" },
    @{ Name = "Coding Precise"; Description = "Thinking ON + preserve, lower temp for precise code generation"; File = "coding-precise.json" },
    @{ Name = "Fast Chat"; Description = "Thinking OFF, faster responses for general conversation"; File = "fast-chat.json" },
    @{ Name = "Deep Reasoning"; Description = "Thinking ON + preserve, 131K context for complex planning"; File = "deep-reasoning.json" },
    @{ Name = "Max Context"; Description = "Thinking ON + preserve, full 262K context window"; File = "max-context.json" }
)

function Get-BuiltInPresets {
    return $Script:BuiltInPresets
}

function Get-AllPresets {
    $presets = @($Script:BuiltInPresets)
    $userPresets = Get-UserPresets
    $presets += $userPresets
    return $presets
}

function Get-UserPresets {
    $presets = @()
    if (Test-Path $Script:PresetsDir) {
        $files = Get-ChildItem -Path $Script:PresetsDir -Filter "*.json" -File
        foreach ($file in $files) {
            if ($file.BaseName -notmatch '^agentic-ai|^coding-precise|^fast-chat|^deep-reasoning|^max-context') {
                try {
                    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
                    if ($content) {
                        $preset = $content | ConvertFrom-Json
                        $presets += @{
                            Name = $file.BaseName -replace '-', ' '
                            Description = $preset.Description -or "User preset"
                            File = $file.Name
                            IsBuiltIn = $false
                        }
                    }
                } catch { }
            }
        }
    }
    return $presets
}

function Load-Preset {
    param([string]$PresetName)

    $presetFile = $null
    $isBuiltIn = $false

    # Check built-in presets first
    $builtIn = $Script:BuiltInPresets | Where-Object { $_.Name -eq $PresetName }
    if ($builtIn) {
        $presetFile = Join-Path $Script:PresetsDir $builtIn.File
        $isBuiltIn = $true
    }

    # Check user presets
    if (-not $presetFile) {
        $userFile = Join-Path $Script:PresetsDir "$($PresetName -replace ' ', '-').json"
        if (Test-Path $userFile) {
            $presetFile = $userFile
        }
    }

    if (-not $presetFile -or -not (Test-Path $presetFile)) {
        return $null
    }

    try {
        $content = Get-Content $presetFile -Raw -ErrorAction SilentlyContinue
        if ($content) {
            $preset = $content | ConvertFrom-Json
            $preset | Add-Member -MemberType NoteProperty -Name "IsBuiltIn" -Value $isBuiltIn -Force
            return $preset
        }
    } catch {
        Write-Error "Failed to load preset: $PresetName"
    }

    return $null
}

function Save-Preset {
    param(
        [string]$Name,
        [string]$Description = "",
        [hashtable]$Settings
    )

    $filename = "$($Name -replace '[^a-zA-Z0-9]', '-')".Trim('-') + ".json"
    $filepath = Join-Path $Script:PresetsDir $filename

    $presetObj = @{
        Name = $Name
        Description = $Description
        Created = (Get-Date).ToString("yyyy-MM-dd HH:mm")
        Settings = $Settings
    }

    $presetObj | ConvertTo-Json -Depth 5 | Set-Content $filepath -Encoding UTF8
    return $filepath
}

function Delete-UserPreset {
    param([string]$Name)

    $filename = "$($Name -replace ' ', '-')".Trim('-') + ".json"
    $filepath = Join-Path $Script:PresetsDir $filename

    if (Test-Path $filepath) {
        Remove-Item $filepath -Force
        return $true
    }
    return $false
}

function Save-Session {
    param([hashtable]$Settings)

    $session = @{
        LastPreset = $Settings.PresetName
        LastModel = $Settings.ModelPath
        GpuLayers = $Settings.GpuLayers
        NcpuMoe = $Settings.NcpuMoe
        CtxSize = $Settings.CtxSize
        Threads = $Settings.Threads
        BatchSize = $Settings.BatchSize
        UBatchSize = $Settings.UBatchSize
        Temp = $Settings.Temp
        TopP = $Settings.TopP
        TopK = $Settings.TopK
        MinP = $Settings.MinP
        TypicalP = $Settings.TypicalP
        RepeatPenalty = $Settings.RepeatPenalty
        RepeatLastN = $Settings.RepeatLastN
        PresencePenalty = $Settings.PresencePenalty
        FreqPenalty = $Settings.FreqPenalty
        CacheTypeK = $Settings.CacheTypeK
        CacheTypeV = $Settings.CacheTypeV
        FlashAttn = $Settings.FlashAttn
        SplitMode = $Settings.SplitMode
        TensorSplit = $Settings.TensorSplit
        Mlock = $Settings.Mlock
        NoMmap = $Settings.NoMmap
        Host = $Settings.Host
        Port = $Settings.Port
        Parallel = $Settings.Parallel
        ApiKey = $Settings.ApiKey
        Alias = $Settings.Alias
        Thinking = $Settings.Thinking
        PreserveThinking = $Settings.PreserveThinking
        ReasoningFormat = $Settings.ReasoningFormat
        ReasoningBudget = $Settings.ReasoningBudget
        Jinja = $Settings.Jinja
        Webui = $Settings.Webui
        Metrics = $Settings.Metrics
        ContBatching = $Settings.ContBatching
        DryMultiplier = $Settings.DryMultiplier
        DryBase = $Settings.DryBase
        DryAllowed = $Settings.DryAllowed
        XtcProb = $Settings.XtcProb
        XtcThresh = $Settings.XtcThresh
        Seed = $Settings.Seed
        SavedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }

    $session | ConvertTo-Json -Depth 5 | Set-Content $Script:SessionFile -Encoding UTF8
}

function Get-LastSession {
    if (Test-Path $Script:SessionFile) {
        try {
            $content = Get-Content $Script:SessionFile -Raw -ErrorAction SilentlyContinue
            if ($content) {
                return $content | ConvertFrom-Json
            }
        } catch { }
    }
    return $null
}

function Save-ModelRegistry {
    param([hashtable]$Models)

    $lines = @("# Model registry - alias=config_path", "# No spaces around =")
    foreach ($alias in $Models.Keys) {
        $lines += "$alias=$($Models[$alias])"
    }
    $lines -join "`n" | Set-Content $Script:RegistryFile -Encoding UTF8
}

function Get-ModelRegistry {
    $models = @{}
    if (Test-Path $Script:RegistryFile) {
        try {
            $content = Get-Content $Script:RegistryFile
            foreach ($line in $content) {
                if ($line -match '^\s*([^#=]+)=([^#]+)' -and $line -notmatch '^\s*#') {
                    $alias = $Matches[1].Trim()
                    $path = $Matches[2].Trim()
                    if ($alias -and $path) {
                        $models[$alias] = $path
                    }
                }
            }
        } catch { }
    }
    return $models
}

function Add-ModelToRegistry {
    param(
        [string]$Alias,
        [string]$ConfigPath
    )

    $registry = Get-ModelRegistry
    $registry[$Alias] = $ConfigPath
    Save-ModelRegistry -Models $registry
}

function Remove-ModelFromRegistry {
    param([string]$Alias)

    $registry = Get-ModelRegistry
    if ($registry.ContainsKey($Alias)) {
        $registry.Remove($Alias)
        Save-ModelRegistry -Models $registry
        return $true
    }
    return $false
}

function Scan-Models {
    param(
        [string[]]$SearchPaths,
        [string]$RegistryFile
    )

    $models = @{}
    $ggufPattern = "*.gguf"

    foreach ($searchPath in $SearchPaths) {
        if (-not (Test-Path $searchPath)) { continue }

        $ggufFiles = Get-ChildItem -Path $searchPath -Filter $ggufPattern -File -ErrorAction SilentlyContinue
        foreach ($file in $ggufFiles) {
            if ($file.BaseName -match '^mmproj') { continue }

            $sizeGB = [math]::Round($file.Length / 1GB, 1)
            $name = $file.BaseName
            $alias = $name -replace '[^a-zA-Z0-9]', '_'

            # Generate a friendly alias
            $friendlyAlias = ($name -replace '[-_]', ' ').Trim() -replace '\s+', ' '

            # Check if already in registry
            $existingRegistry = Get-ModelRegistry
            $foundAlias = $null
            foreach ($regAlias in $existingRegistry.Keys) {
                if ($existingRegistry[$regAlias] -eq $file.FullName) {
                    $foundAlias = $regAlias
                    break
                }
            }

            if ($foundAlias) {
                $models[$foundAlias] = @{
                    Path = $file.FullName
                    Name = $name
                    SizeGB = $sizeGB
                    Alias = $foundAlias
                    Directory = (Split-Path $file.DirectoryName -Leaf)
                }
            } else {
                $models[$friendlyAlias] = @{
                    Path = $file.FullName
                    Name = $name
                    SizeGB = $sizeGB
                    Alias = $friendlyAlias
                    Directory = (Split-Path $file.DirectoryName -Leaf)
                }
            }
        }
    }

    return $models
}

function Set-RuntimePath {
    param([string]$Path)

    if ($Path) { $Path = $Path.Trim() }
    $Path | Set-Content $Script:RuntimePathFile -Encoding UTF8
}

function Get-RuntimePath {
    if (Test-Path $Script:RuntimePathFile) {
        $path = Get-Content $Script:RuntimePathFile -Raw
        if ($path -and (Test-Path $path)) {
            return $path.Trim()
        }
    }
    return $null
}

# --- HuggingFace GGUF Model Download ---
$Script:HfCacheDir = Join-Path $env:USERPROFILE ".cache\huggingface\hf_download"
New-Item -ItemType Directory -Force -Path $Script:HfCacheDir | Out-Null

function Search-HfModels {
    param(
        [string]$Query,
        [int]$Limit = 10
    )

    try {
        $url = "https://huggingface.co/api/models?search=$([System.Net.WebUtility]::UrlEncode($Query))&sort=downloads&direction=-1&limit=$Limit&full=false&config=gguf"
        $response = Invoke-RestMethod -Uri $url -TimeoutSec 15 -ErrorAction Stop
        return $response | ForEach-Object {
            @{
                Id         = $_.id
                Author     = $_.author
                Name       = $_.id.Split('/')[-1]
                Downloads  = $_.downloads
                Likes      = $_.likes
                Tags       = $_.tags
                Size       = if ($_.sizes -and $_.sizes.present) { [math]::Round($_.sizes.present / 1GB, 1) } else { $null }
                GgufFiles  = @()
            }
        }
    } catch {
        Write-Host "Search failed: $_" -ForegroundColor Red
        return @()
    }
}

function Get-HfModelFiles {
    param(
        [string]$ModelId
    )

    try {
        $url = "https://huggingface.co/api/models/$ModelId"
        $response = Invoke-RestMethod -Uri $url -TimeoutSec 15 -ErrorAction Stop
        $files = @()
        foreach ($sibling in $response.siblings) {
            $filename = $sibling.rfilename
            if ($filename -and $filename -match '\.gguf$') {
                $files += @{
                    Filename = $filename
                    Size     = if ($sibling.size) { [math]::Round($sibling.size / 1GB, 1) } else { $null }
                    Path     = $filename
                }
            }
        }
        return $files
    } catch {
        Write-Host ("Failed to get model files for {0}: {1}" -f $ModelId, $_) -ForegroundColor Red
        return @()
    }
}

function Download-HfGguf {
    param(
        [string]$ModelId,
        [string]$Filename,
        [scriptblock]$OnProgress,
        [scriptblock]$OnComplete
    )

    $destDir = Join-Path $Script:HfCacheDir $ModelId.Replace('/', '__')
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $destPath = Join-Path $destDir $Filename

    if (Test-Path $destPath) {
        Write-Host "File already exists: $destPath"
        if ($OnComplete) { & $OnComplete $destPath }
        return $destPath
    }

    $url = "https://huggingface.co/$ModelId/resolve/main/$Filename"
    Write-Host "Downloading $Filename from $ModelId..."
    Write-Host "  URL: $url"
    Write-Host "  Destination: $destPath"

    try {
        Invoke-WebRequest -Uri $url -OutFile $destPath -ErrorAction Stop
        $sizeGB = [math]::Round((Get-Item $destPath).Length / 1GB, 1)
        Write-Host "Download complete: $destPath ($sizeGB GB)" -ForegroundColor Green
        if ($OnComplete) { & $OnComplete $destPath }
        return $destPath
    } catch {
        Write-Host "Download failed: $_" -ForegroundColor Red
        if (Test-Path $destPath) { Remove-Item $destPath -Force -ErrorAction SilentlyContinue }
        return $null
    }
}

function Get-RecommendedSmallModels {
    param(
        [int]$MaxSizeGB = 4
    )

    $recommendations = @(
        @{
            Id         = "lmstudio-community/Qwen2.5-1.5B-Instruct-GGUF"
            Name       = "Qwen2.5-1.5B-Instruct"
            Size       = "~1GB (Q4_K_M)"
            Description = "Tiny, fast. Great for testing. 1.5B params."
            BestFor    = "Testing, quick prototyping"
        },
        @{
            Id         = "lmstudio-community/Qwen2.5-3B-Instruct-GGUF"
            Name       = "Qwen2.5-3B-Instruct"
            Size       = "~2GB (Q4_K_M)"
            Description = "Surprisingly capable for its size. 3B params."
            BestFor    = "General chat, fast responses"
        },
        @{
            Id         = "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
            Name       = "Qwen2.5-7B-Instruct"
            Size       = "~4.8GB (Q4_K_M)"
            Description = "Sweet spot for quality/speed. 7B params."
            BestFor    = "Balanced performance"
        },
        @{
            Id         = "lmstudio-community/Phi-3.5-mini-instruct-GGUF"
            Name       = "Phi-3.5-mini-4K"
            Size       = "~2.2GB (Q4_K_M)"
            Description = "Microsoft's efficient 3.8B model. 4K context."
            BestFor    = "Efficient reasoning, coding"
        },
        @{
            Id         = "lmstudio-community/gemma-3-1b-it-GGUF"
            Name       = "Gemma-3-1B-IT"
            Size       = "~0.7GB (Q4_K_M)"
            Description = "Google's tiny 1B model. Ultra-fast."
            BestFor    = "Ultra-fast inference, testing"
        },
        @{
            Id         = "lmstudio-community/Meta-Llama-3.2-3B-Instruct-GGUF"
            Name       = "Llama-3.2-3B-Instruct"
            Size       = "~2GB (Q4_K_M)"
            Description = "Meta's latest small model. 3B params."
            BestFor    = "General purpose, coding"
        }
    )

    return $recommendations | Where-Object {
        $sizeNum = 999
        if ($_.Size -match '^\~?(\d+)') { $sizeNum = [int]$Matches[1] }
        $sizeNum -le $MaxSizeGB -or $_.Size -match '^\~?0\.'
    }
}
