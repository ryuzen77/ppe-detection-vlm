<script lang="ts">
  // Riwayat pemeriksaan satu pekerja (T79), terbaru dulu, berhalaman lewat `before`.
  import { api, ApiError } from '../../lib/api/client'
  import type { WorkerInspection } from '../../lib/api/types'
  import { WORKERS_PAGE as TEXT } from '../../lib/messages'
  import { WORKERS_PAGE } from '../../lib/settings'
  import { extractApiError } from '../../lib/api/error'
  import { formatShortDateTime } from '../../lib/workers'

  interface Props {
    workerId: number
  }

  let { workerId }: Props = $props()

  let items = $state<WorkerInspection[]>([])
  let nextBefore = $state<number | null>(null)
  let loading = $state(false)
  let error = $state('')
  let unavailable = $state(false)

  async function load(before?: number) {
    loading = true
    error = ''
    try {
      const page = await api.workerInspections(workerId, { limit: WORKERS_PAGE.historyPageSize, before })
      items = before ? [...items, ...page.items] : page.items
      nextBefore = page.next_before
    } catch (e) {
      // Server tanpa T79a: rute belum ada -> bukan galat bagi admin, cukup diberi tahu
      if (e instanceof ApiError && e.status === 404) unavailable = true
      else error = extractApiError(e, TEXT.historyUnavailable)
    } finally {
      loading = false
    }
  }

  $effect(() => {
    void workerId
    items = []
    nextBefore = null
    unavailable = false
    load()
  })
</script>

{#if unavailable}
  <p class="note">{TEXT.historyUnavailable}</p>
{:else if error}
  <p class="note error" role="alert">{error}</p>
{:else if !loading && items.length === 0}
  <p class="note">{TEXT.historyEmpty}</p>
{:else}
  <ul class="history">
    {#each items as item (item.id)}
      <li>
        <span class="when mono">{formatShortDateTime(item.timestamp)}</span>
        <span class="result" class:fail={!item.is_complete}
          >{item.is_complete ? TEXT.historyPass : TEXT.historyFail}</span
        >
        <span class="detail">
          {item.missing_items.join(', ')}
          {#if item.fr_score != null}<span class="score">{TEXT.historyScore(item.fr_score)}</span>{/if}
        </span>
        {#if item.snapshot_filename}
          <a class="photo" href={api.snapshotUrl(item.snapshot_filename)} target="_blank" rel="noopener"
            >{TEXT.historyPhoto}</a
          >
        {/if}
      </li>
    {/each}
  </ul>
  {#if nextBefore !== null}
    <button type="button" class="btn" onclick={() => load(nextBefore ?? undefined)} disabled={loading}
      >{TEXT.historyMore}</button
    >
  {/if}
{/if}

<style>
  .note {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .note.error {
    color: var(--danger);
  }
  .history {
    list-style: none;
    margin: 0 0 var(--space-3);
    padding: 0;
    font-size: var(--text-sm);
  }
  li {
    display: grid;
    grid-template-columns: auto auto 1fr auto;
    align-items: baseline;
    gap: var(--space-3);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--border);
  }
  .when {
    color: var(--text-muted);
  }
  .result {
    font-weight: 600;
    color: var(--ok);
  }
  .result.fail {
    color: var(--danger);
  }
  .detail {
    min-width: 0;
    color: var(--text-muted);
  }
  .score {
    margin-left: var(--space-2);
    color: var(--text-faint);
    font-size: var(--text-xs);
  }
  .photo {
    font-size: var(--text-xs);
  }
</style>
