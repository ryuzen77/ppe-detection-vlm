<script lang="ts">
  // Notifikasi kejadian penting saat operator tidak di halaman Monitoring
  import CircleCheck from '@lucide/svelte/icons/circle-check'
  import CircleX from '@lucide/svelte/icons/circle-x'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'
  import X from '@lucide/svelte/icons/x'
  import { NOTIFY } from '../lib/messages'
  import { href } from '../lib/router.svelte'
  import { toasts } from '../lib/stores/toasts.svelte'
</script>

<div class="stack" aria-live="polite">
  {#each toasts.items as toast (toast.id)}
    <div class="toast kind-{toast.kind}" role="status">
      <span class="icon">
        {#if toast.kind === 'denied'}<CircleX size={18} />{:else if toast.kind === 'outage'}<TriangleAlert size={18} />{:else}<CircleCheck size={18} />{/if}
      </span>
      <a class="body" href={href('monitoring')} onclick={() => toasts.dismiss(toast.id)}>
        <strong>{toast.title}</strong>
        <span>{toast.detail}</span>
      </a>
      <button class="close" aria-label={NOTIFY.close} onclick={() => toasts.dismiss(toast.id)}><X size={16} /></button>
    </div>
  {/each}
</div>

<style>
  .stack {
    position: fixed;
    right: var(--space-5);
    bottom: var(--space-5);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: min(360px, calc(100vw - 32px));
    z-index: 50;
  }
  .toast {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    background: var(--surface-2);
    border: 1px solid var(--border-strong);
    border-left-width: 3px;
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  }
  .kind-denied {
    border-left-color: var(--danger);
  }
  .kind-denied .icon {
    color: var(--danger);
  }
  .kind-outage {
    border-left-color: var(--warn);
  }
  .kind-outage .icon {
    color: var(--warn);
  }
  .kind-recovered {
    border-left-color: var(--ok);
  }
  .kind-recovered .icon {
    color: var(--ok);
  }
  .icon {
    padding-top: 2px;
  }
  .body {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: var(--text);
    text-decoration: none;
    font-size: var(--text-sm);
  }
  .body span {
    color: var(--text-muted);
  }
  .close {
    border: 0;
    background: none;
    color: var(--text-faint);
    cursor: pointer;
    padding: 2px;
  }
  .close:hover {
    color: var(--text);
  }
</style>
