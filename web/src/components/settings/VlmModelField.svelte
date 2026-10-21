<script lang="ts">
  // Isian model + lencana validasi satu peran VLM (utama / cadangan / lokal darurat T72):
  // dulu disalin per peran di VlmProviders.
  import Server from '@lucide/svelte/icons/server'
  import type { VlmProviderEntry } from '../../lib/api/types'
  import { VLM_SETTINGS } from '../../lib/messages'
  import { validationBadge } from '../../lib/vlmSelection'

  let {
    id,
    provider,
    model = $bindable(),
    disabled,
    showStats = false,
  }: { id: string; provider: VlmProviderEntry | undefined; model: string; disabled: boolean; showStats?: boolean } = $props()

  const entry = $derived(provider?.models.find((m) => m.model === model))
</script>

<label>
  <span>{VLM_SETTINGS.modelLabel}</span>
  <input type="text" bind:value={model} list="models-{id}" {disabled} />
  <datalist id="models-{id}">
    {#each provider?.models || [] as m (m.model)}
      <option value={m.model}></option>
    {/each}
  </datalist>
</label>

{#if entry}
  {@const badge = validationBadge(entry.validated)}
  <div class="meta">
    <span class="badge tone-{badge.tone}">{badge.text}</span>
    {#if provider?.data_location}
      <span class="location" title={VLM_SETTINGS.dataLocation}><Server size={14} /> {provider.data_location}</span>
    {/if}
  </div>
  {#if showStats && entry.photos}
    <div class="stats">{VLM_SETTINGS.stats(entry.photos, entry.missed, entry.false_rejects, entry.median_seconds)}</div>
  {/if}
{/if}

<style>
  label {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: var(--space-3);
  }
  input {
    padding: 6px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--text);
  }
  .meta {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-1);
  }
  .badge {
    padding: 2px 8px;
    border-radius: 999px;
    font-size: var(--text-xs);
    font-weight: 500;
  }
  .tone-ok { background: var(--ok); color: var(--text); }
  .tone-warn { background: var(--warn); color: var(--surface); }
  .tone-muted { background: var(--border-strong); color: var(--text); }
  .location {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  .stats {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
</style>
