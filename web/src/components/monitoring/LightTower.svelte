<script lang="ts">
  // Lampu gerbang (T88): operator sering tidak melihat lampu fisik. Merah & hijau = lampu nyata
  // (baca balik perangkat), kuning = perintah server bila perangkat tidak punya kuning.
  // Teks selalu menyertai warna, supaya terbaca dari jauh / oleh yang sulit membedakan warna.
  import { towerView } from '../../lib/lightTower'
  import { LIGHT_TOWER as TEXT } from '../../lib/messages'
  import { telemetry } from '../../lib/stores/telemetry.svelte'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'

  const view = $derived(towerView(telemetry.data))
  const SOURCE_LABEL = { physical: TEXT.sourcePhysical, plan: TEXT.sourcePlan, unknown: TEXT.unknown }
</script>

<section class="tower tone-{view.tone}" aria-labelledby="tower-title">
  <header>
    <h2 id="tower-title">{TEXT.title}</h2>
    <strong class="state" aria-live="polite">{view.state}</strong>
  </header>

  <ul class="lamps">
    {#each view.lamps as lamp (lamp.lamp)}
      <li class="lamp-item">
        <span
          class="lamp lamp-{lamp.lamp}"
          class:on={lamp.on}
          class:unknown={lamp.source === 'unknown'}
          role="img"
          aria-label="{TEXT.names[lamp.lamp]}: {lamp.source === 'unknown'
            ? TEXT.unknown
            : lamp.on
              ? TEXT.states[lamp.lamp]
              : TEXT.states.off}"
        >
          {#if lamp.source === 'unknown'}?{/if}
        </span>
        <span class="name">{TEXT.names[lamp.lamp]}</span>
        <span class="source">{SOURCE_LABEL[lamp.source]}</span>
      </li>
    {/each}
  </ul>

  {#if view.message}<p class="message">{view.message}</p>{/if}
  {#each view.notes as note (note)}
    <p class="note"><TriangleAlert size={14} aria-hidden="true" /> {note}</p>
  {/each}
</section>

<style>
  .tower {
    padding: var(--space-4);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  h2 {
    margin: 0;
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-muted);
  }
  .state {
    font-size: var(--text-lg);
    letter-spacing: 0.04em;
  }
  .tone-ok .state {
    color: var(--ok);
  }
  .tone-danger .state {
    color: var(--danger);
  }
  .tone-warn .state {
    color: var(--warn);
  }
  .lamps {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .lamp-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-1);
  }
  .lamp {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: 2px solid var(--border-strong);
    background: var(--surface-2);
    color: var(--text-muted);
    font-weight: 700;
    transition:
      background-color 120ms ease,
      box-shadow 120ms ease;
  }
  .lamp.unknown {
    border-style: dashed;
  }
  .lamp-red.on {
    background: var(--danger);
    border-color: var(--danger);
    box-shadow: 0 0 18px var(--danger);
  }
  .lamp-yellow.on {
    background: var(--warn);
    border-color: var(--warn);
    box-shadow: 0 0 18px var(--warn);
  }
  .lamp-green.on {
    background: var(--ok);
    border-color: var(--ok);
    box-shadow: 0 0 18px var(--ok);
  }
  .name {
    font-size: var(--text-sm);
    font-weight: 600;
  }
  .source {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  .message {
    margin: var(--space-3) 0 0;
    font-size: var(--text-sm);
  }
  .note {
    display: flex;
    gap: var(--space-2);
    align-items: flex-start;
    margin: var(--space-2) 0 0;
    font-size: var(--text-xs);
    color: var(--warn);
  }
  @media (prefers-reduced-motion: reduce) {
    .lamp {
      transition: none;
    }
  }
</style>
