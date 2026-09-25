<script lang="ts">
  // Registri ikon garis berdasarkan NAMA ikon dari katalog APD backend
  // (PPEItem.icon_name) — frontend tidak mengenal kunci item seperti "helm".
  // Item baru cukup memakai nama yang sudah ada di sini; nama tak dikenal →
  // perisai umum. Lucide tidak punya celana & rompi, jadi keduanya digambar
  // sendiri dengan gaya yang sama (kanvas 24×24, garis membulat).
  import Hand from '@lucide/svelte/icons/hand'
  import HardHat from '@lucide/svelte/icons/hard-hat'
  import RectangleGoggles from '@lucide/svelte/icons/rectangle-goggles'
  import Shield from '@lucide/svelte/icons/shield'
  import SportShoe from '@lucide/svelte/icons/sport-shoe'

  let { name, size = 18 }: { name: string; size?: number } = $props()

  const LUCIDE = {
    'hard-hat': HardHat,
    'sport-shoe': SportShoe,
    'rectangle-goggles': RectangleGoggles,
    hand: Hand,
  } as const

  /** Ikon gambar sendiri: daftar path SVG per nama */
  const CUSTOM: Record<string, string[]> = {
    // Celana panjang: ikat pinggang & dua kaki
    trousers: ['M6 3h12l1.2 18h-5.4L12 10l-1.8 11H4.8z', 'M6.2 6.5h11.6'],
    // Rompi keselamatan: tanpa lengan, kerah V, pita reflektif
    'safety-vest': ['M9 3 7 4c0 3-2 4-2 6.5V21h14V10.5C19 8 17 7 17 4l-2-1-3 6z', 'M12 9v12', 'M5 15.5h14'],
  }

  const STROKE = 1.75
  const Icon = $derived(LUCIDE[name as keyof typeof LUCIDE] ?? Shield)
  const paths = $derived(CUSTOM[name])
</script>

{#if paths}
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={STROKE}
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    {#each paths as d (d)}<path {d} />{/each}
  </svg>
{:else}
  <Icon {size} strokeWidth={STROKE} aria-hidden="true" />
{/if}
