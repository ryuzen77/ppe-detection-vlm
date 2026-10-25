<script lang="ts">
  // Kerangka dialog modal bersama (T42j): sebelumnya CameraPicker & SnapshotDialog masing-masing
  // menyalin buka/tutup `<dialog>` native + gaya kotak & latar. Esc/tombol tutup bawaan browser
  // memanggil `onclose`, jadi state pemilik selalu ikut tertutup.
  import { untrack, type Snippet } from 'svelte'

  let {
    open,
    onclose,
    onopen,
    labelledby,
    size = 'md',
    closeOnBackdrop = false,
    children,
  }: {
    open: boolean
    onclose: () => void
    /** Dipanggil sekali setiap dialog dibuka (mis. memuat ulang isi) */
    onopen?: () => void
    labelledby: string
    size?: 'md' | 'lg'
    closeOnBackdrop?: boolean
    children: Snippet
  } = $props()

  let dialog: HTMLDialogElement | undefined = $state()

  $effect(() => {
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      // State yang dibaca pemilik saat dibuka tidak boleh menjadi dependensi efek ini
      if (onopen) untrack(onopen)
    } else if (!open && dialog.open) {
      dialog.close()
    }
  })

  // Klik di latar (di luar isi dialog) menutup, bila diizinkan pemilik
  function onBackdrop(e: MouseEvent) {
    if (closeOnBackdrop && e.target === dialog) onclose()
  }
</script>

<dialog bind:this={dialog} class={size} {onclose} onclick={onBackdrop} aria-labelledby={labelledby}>
  {@render children()}
</dialog>

<style>
  dialog {
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    background: var(--surface);
    color: var(--text);
  }
  dialog.md {
    width: min(520px, calc(100vw - 32px));
    padding: var(--space-6);
  }
  dialog.lg {
    width: min(720px, calc(100vw - 32px));
    padding: var(--space-5);
  }
  dialog::backdrop {
    background: var(--backdrop);
  }
</style>
