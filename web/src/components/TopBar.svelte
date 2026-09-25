<script lang="ts">
  // Bilah atas: navigasi + status yang selalu terlihat di semua halaman
  // (keputusan gerbang, kamera, VLM, koneksi, jam) — keputusan UX T33.
  import Camera from '@lucide/svelte/icons/camera'
  import Cpu from '@lucide/svelte/icons/cpu'
  import KeyRound from '@lucide/svelte/icons/key-round'
  import ShieldCheck from '@lucide/svelte/icons/shield-check'
  import WifiOff from '@lucide/svelte/icons/wifi-off'
  import { onDestroy } from 'svelte'
  import { gateView } from '../lib/gate'
  import { ADMIN_TOKEN, BRAND, CONNECTION, GATE_CHIP, NAV, chipTitle } from '../lib/messages'
  import { href, ROUTES, router } from '../lib/router.svelte'
  import { CLOCK } from '../lib/settings'
  import { cameraChip, vlmChip } from '../lib/status'
  import { adminToken } from '../lib/stores/adminToken.svelte'
  import { telemetry } from '../lib/stores/telemetry.svelte'

  let now = $state(new Date())
  const clock = setInterval(() => (now = new Date()), CLOCK.tickMs)
  onDestroy(() => clearInterval(clock))

  const t = $derived(telemetry.data)
  const gate = $derived(gateView(t, telemetry.status))
  const camera = $derived(cameraChip(t))
  const vlm = $derived(vlmChip(t))
</script>

<header class="topbar">
  <div class="brand" title={BRAND.full}>
    <ShieldCheck size={22} strokeWidth={2} aria-hidden="true" />
    <span class="brand-text">
      <span class="brand-name">{BRAND.name}</span>
      <span class="brand-tagline">{BRAND.tagline}</span>
    </span>
  </div>

  <nav aria-label={NAV.label}>
    {#each ROUTES as route (route)}
      <a href={href(route)} aria-current={router.current === route ? 'page' : undefined}>{NAV[route]}</a>
    {/each}
  </nav>

  <div class="status">
    {#if router.current !== 'monitoring' && gate.kind !== 'offline'}
      <a class="gate tone-{gate.tone}" href={href('monitoring')} title={GATE_CHIP.title}>
        <span class="dot"></span>
        <span class="label">{GATE_CHIP.text(gate.title, gate.trackId)}</span>
      </a>
    {/if}
    {#if telemetry.status !== 'connected'}
      <span class="chip tone-danger" title={CONNECTION.lost}><WifiOff size={14} aria-hidden="true" /> <span class="label">{CONNECTION.lost}</span></span>
    {:else}
      <span class="chip tone-{camera.tone}" title={chipTitle(camera.text, camera.hint)}><Camera size={14} aria-hidden="true" /> <span class="label">{camera.text}</span></span>
      <span class="chip tone-{vlm.tone}" title={chipTitle(vlm.text, vlm.hint)}><Cpu size={14} aria-hidden="true" /> <span class="label">{vlm.text}</span></span>
    {/if}
    <button class="key" class:unset={!adminToken.hasToken} onclick={() => adminToken.open()}
            title={adminToken.hasToken ? ADMIN_TOKEN.buttonSet : ADMIN_TOKEN.buttonUnset}
            aria-label={adminToken.hasToken ? ADMIN_TOKEN.buttonSet : ADMIN_TOKEN.buttonUnset}>
      <KeyRound size={16} aria-hidden="true" />
    </button>
    <span class="clock mono">{now.toLocaleTimeString(CLOCK.locale, { hour12: false })}</span>
  </div>
</header>

<style>
  .topbar {
    height: var(--topbar-h);
    display: flex;
    align-items: center;
    gap: var(--space-6);
    padding: 0 var(--space-5);
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text);
  }
  .brand-text {
    display: flex;
    flex-direction: column;
    line-height: 1.1;
  }
  /* Ditulis renggang: D E P R O */
  .brand-name {
    font-weight: 700;
    font-size: var(--text-md);
    letter-spacing: 0.32em;
  }
  .brand-tagline {
    font-size: 0.625rem;
    color: var(--text-muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  nav {
    display: flex;
    gap: var(--space-1);
  }
  nav a {
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    text-decoration: none;
    font-size: var(--text-sm);
    font-weight: 500;
  }
  nav a:hover {
    color: var(--text);
    background: var(--surface-2);
  }
  nav a[aria-current='page'] {
    color: var(--text);
    background: var(--surface-3);
  }
  .brand,
  nav {
    flex-shrink: 0;
  }
  /* Status boleh menyempit: chip dipotong (…) lebih dulu daripada navigasi */
  .status {
    margin-left: auto;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
  }
  .chip,
  .gate {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid var(--border);
    color: var(--text-muted);
    white-space: nowrap;
    min-width: 0;
  }
  .chip :global(svg),
  .dot {
    flex-shrink: 0;
  }
  .label {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .gate {
    text-decoration: none;
    color: var(--text);
    font-weight: 600;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--text-faint);
  }
  .tone-ok {
    color: var(--ok);
    border-color: var(--ok-line);
  }
  .tone-warn {
    color: var(--warn);
    border-color: var(--warn-line);
  }
  .tone-danger {
    color: var(--danger);
    border-color: var(--danger-line);
  }
  .gate.tone-ok .dot {
    background: var(--ok);
  }
  .gate.tone-warn .dot {
    background: var(--warn);
  }
  .gate.tone-danger .dot {
    background: var(--danger);
  }
  /* Tombol token admin: netral (bukan warna status); belum diisi = lebih redup */
  .key {
    display: inline-grid;
    place-items: center;
    flex-shrink: 0;
    width: 30px;
    height: 30px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .key:hover {
    color: var(--text);
    background: var(--surface-2);
  }
  .key.unset {
    color: var(--text-faint);
    border-style: dashed;
  }
  .clock {
    color: var(--text-muted);
    padding-left: var(--space-2);
  }

  /* Jendela sempit (media query tidak bisa memakai var(--...)): tagline &
     jam disembunyikan, lalu chip kamera/VLM tinggal ikon — teks lengkapnya
     tetap di tooltip dan dibacakan pembaca layar. */
  @media (max-width: 1100px) {
    .topbar {
      gap: var(--space-4);
      padding: 0 var(--space-4);
    }
    .brand-tagline,
    .clock {
      display: none;
    }
  }
  @media (max-width: 1000px) {
    .chip .label {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }
    /* Chip ikon tidak ikut menyempit; yang dipotong teks chip gerbang */
    .chip {
      padding: 4px 6px;
      flex-shrink: 0;
    }
  }
  /* Layar ponsel: status pindah ke baris kedua. Aman karena Monitoring
     (satu-satunya pemakai --topbar-h) sudah bertinggi otomatis di < 1100px. */
  @media (max-width: 560px) {
    .topbar {
      height: auto;
      flex-wrap: wrap;
      row-gap: var(--space-2);
      padding: var(--space-2) var(--space-4);
    }
    .status {
      margin-left: 0;
      flex-basis: 100%;
    }
    .brand-text {
      display: none;
    }
    nav a {
      padding: 6px 8px;
    }
  }
</style>
