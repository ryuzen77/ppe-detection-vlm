<script lang="ts">
  // Keputusan gerbang: elemen terbesar di layar (keputusan UX T33).
  import CircleCheck from '@lucide/svelte/icons/circle-check'
  import CircleX from '@lucide/svelte/icons/circle-x'
  import Hourglass from '@lucide/svelte/icons/hourglass'
  import LoaderCircle from '@lucide/svelte/icons/loader-circle'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'
  import UserRound from '@lucide/svelte/icons/user-round'
  import VideoOff from '@lucide/svelte/icons/video-off'
  import WifiOff from '@lucide/svelte/icons/wifi-off'
  import type { GateView } from '../../lib/gate'
  import { GATE } from '../../lib/messages'

  let { gate }: { gate: GateView } = $props()
</script>

<section class="decision tone-{gate.tone}" aria-live="polite" aria-label={GATE.ariaLabel}>
  <div class="icon">
    {#if gate.kind === 'granted'}<CircleCheck size={40} strokeWidth={1.75} />
    {:else if gate.kind === 'denied'}<CircleX size={40} strokeWidth={1.75} />
    {:else if gate.kind === 'waiting'}<Hourglass size={36} strokeWidth={1.75} />
    {:else if gate.kind === 'position'}<TriangleAlert size={36} strokeWidth={1.75} />
    {:else if gate.kind === 'analyzing'}<span class="spin"><LoaderCircle size={36} strokeWidth={1.75} /></span>
    {:else if gate.kind === 'no-camera'}<VideoOff size={36} strokeWidth={1.75} />
    {:else if gate.kind === 'offline'}<WifiOff size={36} strokeWidth={1.75} />
    {:else}<UserRound size={36} strokeWidth={1.75} />{/if}
  </div>

  <div class="text">
    {#if gate.trackId}<span class="subject mono">{GATE.subject(gate.trackId)}</span>{/if}
    <h2 class:big={gate.kind === 'granted' || gate.kind === 'denied'}>{gate.title}</h2>
    <p>{gate.detail}</p>
    {#if gate.missing.length}
      <ul class="missing">
        {#each gate.missing as m (m)}<li>{m}</li>{/each}
      </ul>
    {/if}
    {#if gate.progress !== null}
      <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(gate.progress * 100)}>
        <span style:width="{gate.progress * 100}%"></span>
      </div>
    {/if}
  </div>
</section>

<style>
  .decision {
    display: flex;
    gap: var(--space-4);
    padding: var(--space-5);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border);
    background: var(--surface);
    min-height: 168px;
  }
  .icon {
    color: var(--text-muted);
    padding-top: 2px;
  }
  .text {
    flex: 1;
    min-width: 0;
  }
  .subject {
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  h2 {
    margin: 2px 0 6px;
    font-size: var(--text-xl);
    font-weight: 650;
    line-height: 1.15;
  }
  h2.big {
    font-size: var(--text-2xl);
    letter-spacing: 0.01em;
  }
  p {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .missing {
    margin: var(--space-3) 0 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .missing li {
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--danger-soft);
    color: var(--danger);
    font-size: var(--text-sm);
    font-weight: 600;
  }
  .progress {
    margin-top: var(--space-3);
    height: 4px;
    border-radius: 2px;
    background: var(--surface-3);
    overflow: hidden;
  }
  .progress span {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width 0.2s;
  }

  .tone-ok {
    background: var(--ok-soft);
    border-color: var(--ok-line);
  }
  .tone-ok .icon,
  .tone-ok h2 {
    color: var(--ok);
  }
  .tone-danger {
    background: var(--danger-soft);
    border-color: var(--danger-line);
  }
  .tone-danger .icon,
  .tone-danger h2 {
    color: var(--danger);
  }
  .tone-warn {
    background: var(--warn-soft);
    border-color: var(--warn-line);
  }
  .tone-warn .icon,
  .tone-warn h2 {
    color: var(--warn);
  }

  .spin {
    display: inline-flex;
    animation: spin 1.2s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spin {
      animation: none;
    }
  }
</style>
