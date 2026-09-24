<script lang="ts">
  // Ikon garis per item APD (pengganti emoji dari katalog). Lucide tidak punya
  // ikon celana maupun rompi, jadi keduanya digambar sendiri dengan gaya yang
  // sama (kanvas 24×24, garis membulat). Item baru tanpa pemetaan memakai perisai.
  import Hand from '@lucide/svelte/icons/hand'
  import HardHat from '@lucide/svelte/icons/hard-hat'
  import RectangleGoggles from '@lucide/svelte/icons/rectangle-goggles'
  import Shield from '@lucide/svelte/icons/shield'
  import SportShoe from '@lucide/svelte/icons/sport-shoe'

  let { itemKey, size = 18 }: { itemKey: string; size?: number } = $props()

  const LUCIDE = {
    helm: HardHat,
    sepatu: SportShoe,
    kacamata: RectangleGoggles,
    sarung_tangan: Hand,
  } as const

  const Icon = $derived(LUCIDE[itemKey as keyof typeof LUCIDE] ?? Shield)
</script>

{#if itemKey === 'celana'}
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <!-- Celana panjang: ikat pinggang, dua kaki -->
    <path d="M6 3h12l1.2 18h-5.4L12 10l-1.8 11H4.8z" />
    <path d="M6.2 6.5h11.6" />
  </svg>
{:else if itemKey === 'rompi'}
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <!-- Rompi keselamatan: tanpa lengan, kerah V, pita reflektif -->
    <path d="M9 3 7 4c0 3-2 4-2 6.5V21h14V10.5C19 8 17 7 17 4l-2-1-3 6z" />
    <path d="M12 9v12" />
    <path d="M5 15.5h14" />
  </svg>
{:else}
  <Icon {size} strokeWidth={1.75} aria-hidden="true" />
{/if}
