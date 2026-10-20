<script lang="ts">
  import { onMount } from 'svelte'
  import { health } from '../../lib/stores/health.svelte'
  import { LOCAL_VLM } from '../../lib/messages'
  import {
    localVlmStatusText,
    formatGpuRatio,
    formatLatency,
    formatOtherGpuApps,
    shouldShowGpuAppsWarning
  } from '../../lib/localVlm'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'

  onMount(() => {
    void health.load()
  })

  const vlm = $derived(health.localVlm)
  const statusText = $derived(localVlmStatusText(vlm?.state))
  const gpuText = $derived(formatGpuRatio(vlm?.gpu_ratio))
  const latencyText = $derived(formatLatency(vlm?.last_latency_s))
  const slowStreak = $derived(vlm?.slow_streak ?? 0)
  const otherAppsText = $derived(formatOtherGpuApps(vlm?.other_gpu_apps))
  const showWarning = $derived(shouldShowGpuAppsWarning(vlm))
</script>

<section class="card">
  <h2>{LOCAL_VLM.cardTitle}</h2>

  <div class="info-list">
    <div class="info-row">
      <span class="info-label">{LOCAL_VLM.statusLabel}</span>
      <span class="info-value state-{vlm?.state ?? 'unknown'}">{statusText}</span>
    </div>
    <div class="info-row">
      <span class="info-label">{LOCAL_VLM.gpuRatioLabel}</span>
      <span class="info-value mono">{gpuText}</span>
    </div>
    <div class="info-row">
      <span class="info-label">{LOCAL_VLM.latencyLabel}</span>
      <span class="info-value mono">{latencyText}</span>
    </div>
    <div class="info-row">
      <span class="info-label">{LOCAL_VLM.slowStreakLabel}</span>
      <span class="info-value mono">{slowStreak}</span>
    </div>
    <!-- T78: daftar aplikasi lain hanya saat perlu ditindaklanjuti (VLM lokal lambat/terbagi) -->
    {#if showWarning}
      <div class="info-row">
        <span class="info-label">{LOCAL_VLM.otherAppsLabel}</span>
        <span class="info-value">{otherAppsText}</span>
      </div>
    {/if}
  </div>

  {#if showWarning}
    <div class="warning-banner" role="alert">
      <TriangleAlert size={16} aria-hidden="true" />
      <span>{LOCAL_VLM.closeAppsHint}</span>
    </div>
  {/if}
</section>

<style>
  .card {
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-lg);
  }
  .info-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: var(--text-sm);
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--border);
  }
  .info-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }
  .info-label {
    color: var(--text-muted);
  }
  .info-value {
    font-weight: 500;
    color: var(--text);
  }
  .mono {
    font-family: var(--font-mono);
  }
  .state-ok {
    color: var(--ok);
  }
  .state-slow,
  .state-partial_gpu {
    color: var(--warn);
  }
  .state-unknown {
    color: var(--text-muted);
  }
  .warning-banner {
    margin-top: var(--space-4);
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-3);
    background: var(--warn-soft);
    border: 1px solid var(--warn-line);
    border-radius: var(--radius-sm);
    color: var(--warn);
    font-size: var(--text-sm);
  }
</style>
