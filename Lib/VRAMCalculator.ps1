# VRAMCalculator.ps1
# Estimates VRAM usage for model + KV cache configurations
# Optimized for RTX 5080 (16GB) and Qwen3.6-35B-A3B MoE

function Get-ModelSizeGB {
    param(
        [string]$GgufPath,
        [string]$QuantType
    )

    if ($GgufPath -and (Test-Path $GgufPath)) {
        $bytes = (Get-Item $GgufPath).Length
        return [math]::Round($bytes / 1GB, 2)
    }

    # Fallback estimates by quant type
    $estimates = @{
        "Q6_K"    = 33.0
        "Q8_0"    = 66.0
        "Q4_K_M"  = 21.0
        "Q4_K_S"  = 16.0
        "Q5_K_M"  = 25.0
        "UD-Q3_XXS" = 13.2
    }

    if ($estimates.ContainsKey($QuantType)) {
        return $estimates[$QuantType]
    }

    return 0.0
}

function Get-KVCacheSizeGB {
    param(
        [int]$CtxSize,
        [int]$GpuLayers,
        [int]$TotalLayers,
        [string]$CacheTypeK,
        [string]$CacheTypeV,
        [int]$LayersPerBlock = 10,
        [int]$HiddenDim = 2048,
        [int]$Experts = 256,
        [int]$ActiveExperts = 9,
        [int]$GqaGroups = 1
    )

    # Qwen3.6-35B-A3B: 40 layers, 10 blocks of (3 DeltaNet + 1 Attention)
    # DeltaNet layers have smaller KV than attention layers
    # Attention layers: GQA with groups
    # For MoE: KV cache is per-layer, not per-expert

    $attentionLayers = 10  # 10 attention blocks
    $deltanetLayers = 30   # 30 DeltaNet layers (smaller KV)

    # Compression factors (vs fp16)
    $compression = @{
        "f16"     = 1.0
        "q8_0"    = 2.0
        "q4_0"    = 4.0
        "turbo4"  = 3.8
        "turbo3"  = 4.9
    }

    if ($compression.ContainsKey($CacheTypeK)) { $compK = $compression[$CacheTypeK] } else { $compK = 1.0 }
    if ($compression.ContainsKey($CacheTypeV)) { $compV = $compression[$CacheTypeV] } else { $compV = 1.0 }

    # DeltaNet KV cache is much smaller (linear attention)
    # DeltaNet KV: ~8 bytes per token per layer (just a single state vector)
    # Attention KV: standard transformer KV cache

    $deltaNetKVBytes = 8  # ~8 bytes per token for DeltaNet (much smaller than attention)
    $attentionKVBytes = 0

    # Attention KV per layer (K + V in fp16 = 4 bytes per head per token)
    # Qwen3.6 uses GQA - estimate ~32 heads effective
    $attentionKVBytes = $HiddenDim * 2 * 2  # K + V, each in fp16 (2 bytes)

    # Only GPU layers contribute to VRAM KV cache
    $gpuAttentionLayers = [math]::Round($attentionLayers * ($GpuLayers / $TotalLayers))
    $gpuDeltaNetLayers = $GpuLayers - $gpuAttentionLayers
    if ($gpuDeltaNetLayers -lt 0) { $gpuDeltaNetLayers = 0 }
    if ($gpuAttentionLayers -lt 0) { $gpuAttentionLayers = 0 }

    # KV cache size in bytes
    $kvBytes = 0
    $kvBytes += ($gpuAttentionLayers * $attentionKVBytes / $compK) * $CtxSize
    $kvBytes += ($gpuDeltaNetLayers * $deltaNetKVBytes / $compK) * $CtxSize

    return [math]::Round($kvBytes / 1GB, 2)
}

function Calculate-TotalVRAM {
    param(
        [string]$GgufPath,
        [string]$QuantType,
        [int]$CtxSize,
        [int]$GpuLayers,
        [int]$TotalLayers = 40,
        [string]$CacheTypeK,
        [string]$CacheTypeV,
        [double]$AvailableVRAM = 16.0,
        [int]$NcpuMoe = 0
    )

    $modelSize = Get-ModelSizeGB -GgufPath $GgufPath -QuantType $QuantType
    $kvCacheSize = Get-KVCacheSizeGB -CtxSize $CtxSize -GpuLayers $GpuLayers `
        -TotalLayers $TotalLayers -CacheTypeK $CacheTypeK -CacheTypeV $CacheTypeV

    # Partial model on GPU: estimate fraction based on layer ratio
    # For MoE with cpu-moe: MoE layers on CPU reduce GPU VRAM significantly
    # MoE experts are ~40% of model size, offloading them saves ~40% of those layer's VRAM
    $layerRatio = $GpuLayers / $TotalLayers
    $gpuModelSize = $modelSize * $layerRatio

    # If CPU MoE is enabled, reduce GPU model size estimate
    if ($NcpuMoe -and [int]$NcpuMoe -gt 0) {
        $moeRatio = [int]$NcpuMoe / $TotalLayers
        $moeSavings = $modelSize * $moeRatio * 0.6  # ~60% savings on MoE layers
        $gpuModelSize = [math]::Max($gpuModelSize - $moeSavings, $modelSize * 0.3)
    }

    # Overhead for CUDA, runtime, OS (~1-2 GB)
    $overhead = 1.5

    $totalVram = $gpuModelSize + $kvCacheSize + $overhead
    $remaining = $AvailableVRAM - $totalVram

    return [PSCustomObject]@{
        ModelSizeGB       = $modelSize
        GpuModelSizeGB    = [math]::Round($gpuModelSize, 2)
        KvCacheSizeGB     = $kvCacheSize
        OverheadGB        = $overhead
        TotalVRAMGB       = [math]::Round($totalVram, 2)
        RemainingGB       = [math]::Round($remaining, 2)
        AvailableVRAM     = $AvailableVRAM
        IsOverLimit       = $remaining -lt 0
        Warning           = if ($remaining -lt 2) { "Warning: Less than 2GB headroom. Consider reducing context or layers." }
                            elseif ($remaining -lt 0) { "ERROR: Exceeds VRAM! Model will swap to system RAM." }
                            else { "OK" }
    }
}

function Get-RecommendedGpuLayers {
    param(
        [string]$GgufPath,
        [string]$QuantType,
        [int]$CtxSize,
        [string]$CacheTypeK,
        [string]$CacheTypeV,
        [double]$AvailableVRAM = 16.0,
        [int]$TotalLayers = 40
    )

    $modelSize = Get-ModelSizeGB -GgufPath $GgufPath -QuantType $QuantType
    if ($modelSize -eq 0) { $modelSize = 33.0 }

    # Available for model weights (reserve for KV cache + overhead)
    $kvOverhead = 2.0  # minimum KV + CUDA overhead
    $forModel = $AvailableVRAM - $kvOverhead

    # Each layer is roughly modelSize / TotalLayers GB
    $layerSize = $modelSize / $TotalLayers
    $maxLayers = [math]::Floor($forModel / $layerSize)

    # Clamp to total layers
    $maxLayers = [math]::Min($maxLayers, $TotalLayers)
    $maxLayers = [math]::Max($maxLayers, 0)

    return $maxLayers
}
