<script lang="ts">
  // Checklist APD per item: hijau = ada, merah = kurang, kuning = belum dinilai (saat menilai/menunggu),
  // netral = saat siaga (keputusan T50). Satu baris per item, tanpa kotak berlapis.
  import Check from '@lucide/svelte/icons/check'
  import Minus from '@lucide/svelte/icons/minus'
  import X from '@lucide/svelte/icons/x'
  import type { InspectionResult, PpeItem } from '../../lib/api/types'
  import type { GateKind } from '../../lib/gate'
  import { CHECKLIST } from '../../lib/messages'
  import { assessItem } from '../../lib/ppe'
  import PpeIcon from '../PpeIcon.svelte'

  let { items, result, decidedBy, gateKind = 'standby' }: {
    items: PpeItem[]
    result: InspectionResult | null
    decidedBy: string
    gateKind?: GateKind
  } = $props()
</script>

<section class="card" aria-label={CHECKLIST.title}>
  <header>
    <h3>{CHECKLIST.title}</h3>
    {#if decidedBy === 'cadangan'}
      <span class="backup" title={CHECKLIST.backupHint}>{CHECKLIST.backupBadge}</span>
    {:else if decidedBy === 'darurat'}
      <span class="backup" title={CHECKLIST.localHint}>{CHECKLIST.localBadge}</span>
    {/if}
  </header>
  <ul>
    {#each items as item (item.key)}
      {@const a = assessItem(item, result?.items?.[item.key], gateKind)}
      <li class="st-{a.status} tone-{a.tone}">
        <span class="item-icon"><PpeIcon name={item.icon_name} /></span>
        <span class="name">{item.label}</span>
        <span class="state">
          {#if a.status === 'ok'}<Check size={16} strokeWidth={2.5} />
          {:else if a.status === 'missing'}<X size={16} strokeWidth={2.5} />
          {:else}<Minus size={16} strokeWidth={2.5} />{/if}
          <span class="state-text">{a.text}</span>
        </span>
      </li>
    {:else}
      <li class="empty">{CHECKLIST.loading}</li>
    {/each}
  </ul>
</section>

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--space-4) var(--space-5);
  }
  header {
    display: flex;
    align-items: center;
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
  .backup {
    font-size: var(--text-xs);
    color: var(--warn);
    border: 1px solid var(--warn-line);
    border-radius: 999px;
    padding: 2px 8px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: grid;
    grid-template-columns: 28px 1fr auto;
    align-items: center;
    gap: var(--space-2);
    padding: 9px 0;
    border-top: 1px solid var(--border);
  }
  li:first-child {
    border-top: 0;
  }
  .item-icon {
    color: var(--text-muted);
    display: inline-flex;
  }
  .name {
    font-weight: 500;
  }
  .state {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-sm);
  }
  .tone-ok .state,
  .st-ok .state {
    color: var(--ok);
  }
  .tone-danger .state,
  .st-missing .state {
    color: var(--danger);
    font-weight: 600;
  }
  .tone-warn .state,
  .st-pending .state {
    color: var(--warn);
  }
  .tone-neutral .state {
    color: var(--text-muted);
  }
  .empty {
    color: var(--text-faint);
    display: block;
  }
</style>
