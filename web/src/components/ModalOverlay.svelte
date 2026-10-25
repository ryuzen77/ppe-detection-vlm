<script lang="ts">
  // Latar + kartu modal berbasis `div` (T42k): sebelumnya disalin di 7 modal Pekerja & Akun.
  // Sengaja bukan `<dialog>` native (lihat ModalDialog): Esc tidak menutup formulir yang sedang
  // diisi; modal yang butuh Esc (Foto, Organisasi) menanganinya sendiri beserta penjaganya.
  import type { Snippet } from 'svelte'

  let {
    labelledby,
    size = 'md',
    scroll = false,
    children,
  }: {
    labelledby: string
    /** sm 400 · md 520 · lg 540 · xl 760 px (lebar lama tiap modal dipertahankan) */
    size?: 'sm' | 'md' | 'lg' | 'xl'
    /** Isi lebih tinggi dari layar laptop 768 px: kartu digulir, tombol tetap terjangkau */
    scroll?: boolean
    children: Snippet
  } = $props()
</script>

<div class="overlay" role="dialog" aria-modal="true" aria-labelledby={labelledby}>
  <div class="card {size}" class:scroll>
    {@render children()}
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4);
    background: var(--backdrop);
  }
  .card {
    width: 100%;
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    box-shadow: 0 10px 25px var(--backdrop);
  }
  .sm {
    max-width: 400px;
  }
  .md {
    max-width: 520px;
  }
  .lg {
    max-width: 540px;
  }
  .xl {
    max-width: 760px;
  }
  .scroll {
    max-height: calc(100dvh - 2 * var(--space-4));
    overflow-y: auto;
  }
</style>
