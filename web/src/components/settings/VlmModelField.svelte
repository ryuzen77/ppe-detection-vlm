<script lang="ts">
  // Isian model + lencana validasi satu peran VLM (utama / cadangan / lokal darurat T72):
  // dulu disalin per peran di VlmProviders. T97: dropdown dari daftar model penyedia untuk key
  // peran ini; teks bebas hanya bila daftar gagal diambil.
  import { untrack } from 'svelte'
  import Server from '@lucide/svelte/icons/server'
  import RefreshCw from '@lucide/svelte/icons/refresh-cw'
  import { api } from '../../lib/api/client'
  import type { VlmModelsResponse, VlmProviderEntry, VlmRole } from '../../lib/api/types'
  import { VLM_SETTINGS } from '../../lib/messages'
  import {
    groupModels,
    listMatches,
    modelListReason,
    modelOptionLabel,
    modelSelectable,
    needsTest,
    reconcileModel,
    validationBadge,
  } from '../../lib/vlmSelection'

  let {
    role,
    provider,
    model = $bindable(),
    disabled,
    showStats = false,
    busy = $bindable(false),
  }: {
    role: VlmRole
    provider: VlmProviderEntry | undefined
    model: string
    disabled: boolean
    showStats?: boolean
    /** Daftar sedang dimuat — induk mengunci Terapkan (pilihan model belum pasti milik penyedia ini) */
    busy?: boolean
  } = $props()

  let list = $state<VlmModelsResponse | null>(null)
  // Penyedia yang permintaan daftarnya gagal (bukan boolean: galat penyedia lama tidak berlaku untuk yang baru)
  let failedFor = $state<string | null>(null)
  // Penyedia pertama = setelan tersimpan: modelnya dipertahankan walau tidak ada lagi di akun (admin
  // melihatnya ditandai). Hanya ganti penyedia oleh admin yang memilih ulang model.
  let loadedProvider: string | null = null
  let requestSeq = 0

  async function load(refresh: boolean) {
    const name = provider?.name
    if (!name) return
    const seq = ++requestSeq
    const providerChanged = loadedProvider !== null && loadedProvider !== name
    busy = true
    try {
      const res = await api.listVlmModels(name, role, refresh)
      if (seq !== requestSeq) return // jawaban penyedia lama datang terlambat
      list = res
      failedFor = null
      if (res.source === 'provider' && (providerChanged || !model))
        model = reconcileModel(res.models, model, provider?.default_model ?? '')
    } catch {
      if (seq !== requestSeq) return
      list = null
      failedFor = name
    } finally {
      if (seq === requestSeq) {
        busy = false
        loadedProvider = name
      }
    }
  }

  $effect(() => {
    if (provider?.name) untrack(() => load(false))
  })

  const shown = $derived(listMatches(list, provider?.name, role) ? list : null)
  const requestFailed = $derived(!shown && !!provider && failedFor === provider.name)
  const fromProvider = $derived(shown?.source === 'provider' ? shown : null)
  const groups = $derived(groupModels(fromProvider?.models ?? []))
  const modelGroups = $derived([
    { label: VLM_SETTINGS.modelGroupTested, items: groups.tested },
    { label: VLM_SETTINGS.modelGroupUntested, items: groups.untested },
  ])
  const listWarning = $derived(
    requestFailed || shown?.source === 'catalog'
      ? VLM_SETTINGS.modelListFailed(modelListReason(shown?.error ?? null, VLM_SETTINGS.modelListReasons))
      : '',
  )
  const entry = $derived(
    shown?.models.find((m) => m.model === model) ?? provider?.models.find((m) => m.model === model),
  )
  const catalogModels = $derived(shown?.models ?? provider?.models ?? [])
</script>

<label>
  <span class="label-row">
    {VLM_SETTINGS.modelLabel}
    <button type="button" class="reload" onclick={() => load(true)} disabled={disabled || busy}>
      <RefreshCw size={12} />
      {VLM_SETTINGS.reloadModelsBtn}
    </button>
  </span>
  {#if fromProvider}
    <select bind:value={model} disabled={disabled || busy}>
      {#each modelGroups as group (group.label)}
        {#if group.items.length}
          <optgroup label={group.label}>
            {#each group.items as m (m.model)}
              <!-- Model tersimpan yang tidak ada lagi di akun tetap tampil terpilih (ditandai), tidak bisa dipilih ulang -->
              <option value={m.model} disabled={!modelSelectable(m) && m.model !== model}
                >{modelOptionLabel(m, VLM_SETTINGS.modelUnavailable)}</option
              >
            {/each}
          </optgroup>
        {/if}
      {/each}
    </select>
  {:else}
    <input type="text" bind:value={model} list="models-{role}" disabled={disabled || busy} />
    <datalist id="models-{role}">
      {#each catalogModels as m (m.model)}
        <option value={m.model}></option>
      {/each}
    </datalist>
  {/if}
</label>

{#if busy && !shown}
  <p class="hint">{VLM_SETTINGS.modelListLoading}</p>
{:else if listWarning}
  <p class="hint warn">{listWarning}</p>
{/if}

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
{#if model && needsTest(entry?.validated ?? 'unvalidated')}
  <p class="hint">{VLM_SETTINGS.testFirstHint}</p>
{/if}

<style>
  label {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: var(--space-3);
  }
  .label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .reload {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 6px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .reload:disabled {
    cursor: default;
    opacity: 0.6;
  }
  input,
  select {
    padding: 6px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--text);
  }
  .hint {
    font-size: var(--text-sm);
    color: var(--text-muted);
    margin: 0 0 var(--space-2);
  }
  .hint.warn {
    color: var(--warn);
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
  .tone-ok {
    background: var(--ok);
    color: var(--text);
  }
  .tone-warn {
    background: var(--warn);
    color: var(--surface);
  }
  .tone-muted {
    background: var(--border-strong);
    color: var(--text);
  }
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
