<script lang="ts">
  // Halaman yang belum dipindahkan ke UI baru (langkah 2 & 3 T33). Selama itu
  // fungsinya tetap tersedia di UI lama.
  import { PAGES } from '../lib/messages'
  import { URLS } from '../lib/settings'

  let { title, description }: { title: string; description: string } = $props()
</script>

<div class="wrap">
  <section class="card">
    <h1>{title}</h1>
    <p>{description}</p>
    <p class="note">{PAGES.notMigrated}</p>
    <a class="btn btn-primary" href={URLS.legacy}>{PAGES.openLegacy}</a>
  </section>
</div>

<style>
  .wrap {
    padding: var(--space-8) var(--space-4);
    display: flex;
    justify-content: center;
  }
  .card {
    width: min(560px, 100%);
    padding: var(--space-8);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
  }
  h1 {
    margin: 0 0 var(--space-2);
    font-size: var(--text-xl);
  }
  p {
    color: var(--text-muted);
  }
  .note {
    font-size: var(--text-sm);
  }
  a.btn {
    text-decoration: none;
  }
</style>
