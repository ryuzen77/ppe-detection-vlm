<script lang="ts">
  import type { HistoryRecord } from '../../lib/api/types'
  import { describeSource } from '../../lib/format'
  import { HISTORY, seconds } from '../../lib/messages'
  import { href } from '../../lib/router.svelte'

  let { records }: { records: HistoryRecord[] } = $props()
</script>

<section class="card" aria-label={HISTORY.ariaLabel}>
  <header>
    <h3>{HISTORY.title}</h3>
    <a href={href('laporan')}>{HISTORY.allReports}</a>
  </header>
  {#if records.length === 0}
    <p class="empty">{HISTORY.empty}</p>
  {:else}
    <ul>
      {#each records as r (r.track_id + r.timestamp + r.snapshot_filename)}
        {@const src = describeSource(r.inference_source)}
        <li>
          <span class="time mono">{r.timestamp}</span>
          <span class="who mono">#{r.track_id}</span>
          <span class="result" class:ok={r.is_complete} class:bad={!r.is_complete}>
            {r.is_complete ? HISTORY.passed : HISTORY.denied}
          </span>
          <span class="detail">
            {r.is_complete ? HISTORY.complete : r.missing_items.join(', ') || HISTORY.incomplete}
          </span>
          <span class="meta">
            {#if src.role === 'cadangan'}<span class="backup">{HISTORY.backup}</span>{/if}
            <span class="mono">{seconds(r.inference_time_ms)}</span>
          </span>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--space-4) var(--space-5);
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: var(--space-2);
  }
  h3 {
    margin: 0;
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-muted);
    letter-spacing: 0.06em;
  }
  header a {
    font-size: var(--text-sm);
    text-decoration: none;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
  }
  li {
    display: grid;
    grid-template-columns: auto auto auto 1fr auto;
    align-items: center;
    gap: var(--space-3);
    padding: 8px 0;
    border-top: 1px solid var(--border);
    font-size: var(--text-sm);
  }
  li:first-child {
    border-top: 0;
  }
  .time,
  .who {
    color: var(--text-muted);
  }
  .result {
    font-weight: 600;
  }
  .ok {
    color: var(--ok);
  }
  .bad {
    color: var(--danger);
  }
  .detail {
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta {
    display: inline-flex;
    gap: var(--space-2);
    color: var(--text-faint);
  }
  .backup {
    color: var(--warn);
  }
  .empty {
    margin: var(--space-2) 0 0;
    color: var(--text-faint);
    font-size: var(--text-sm);
  }
</style>
