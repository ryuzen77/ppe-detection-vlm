<script lang="ts">
  import Camera from '@lucide/svelte/icons/camera'
  import Cpu from '@lucide/svelte/icons/cpu'
  import Globe from '@lucide/svelte/icons/globe'
  import HardDrive from '@lucide/svelte/icons/hard-drive'
  import Lightbulb from '@lucide/svelte/icons/lightbulb'
  import ShieldCheck from '@lucide/svelte/icons/shield-check'
  import WifiOff from '@lucide/svelte/icons/wifi-off'
  import ChevronDown from '@lucide/svelte/icons/chevron-down'
  import LogIn from '@lucide/svelte/icons/log-in'
  import LogOut from '@lucide/svelte/icons/log-out'
  import User from '@lucide/svelte/icons/user'
  import { onDestroy } from 'svelte'
  import { gateView } from '../lib/gate'
  import { BRAND, CONNECTION, GATE_CHIP, NAV, SYSTEM_STATUS, AUTH, chipTitle } from '../lib/messages'
  import { href, ROUTES, router } from '../lib/router.svelte'
  import { CLOCK } from '../lib/settings'
  import { cameraChip, vlmChip, iotChip, internetChip, localStandbyChip, systemSummary } from '../lib/status'
  import { connectionView } from '../lib/connection'
  import { session } from '../lib/stores/session.svelte'
  import { LOGIN } from '../lib/messages'
  import { telemetry } from '../lib/stores/telemetry.svelte'
  import { health } from '../lib/stores/health.svelte'
  import { localVlmChipView } from '../lib/localVlm'

  let now = $state(new Date())
  const clock = setInterval(() => (now = new Date()), CLOCK.tickMs)
  onDestroy(() => clearInterval(clock))

  const t = $derived(telemetry.data)
  const gate = $derived(gateView(t, telemetry.status))
  const camera = $derived(cameraChip(t))
  const vlm = $derived(vlmChip(t))
  const iot = $derived(iotChip(t))
  const internet = $derived(internetChip(t))
  const localStandby = $derived(localStandbyChip(t))
  const connection = $derived(connectionView(session.authenticated, telemetry.status))
  const localVlm = $derived(localVlmChipView(health.localVlm))
  // T78: satu ringkasan menggantikan chip kamera/VLM/lampu/VLM lokal yang berdampingan
  const items = $derived([
    { icon: Camera, ...camera },
    { icon: Cpu, ...vlm },
    ...(internet ? [{ icon: Globe, ...internet }] : []),
    ...(localStandby ? [{ icon: HardDrive, ...localStandby }] : []),
    ...(t?.iot ? [{ icon: Lightbulb, ...iot }] : []),
    ...(localVlm ? [{ icon: Cpu, ...localVlm }] : []),
  ])
  const summary = $derived(systemSummary(items))
  // Chip gerbang "kamera belum siap" sama dengan masalah kamera di ringkasan: tidak ditampilkan dua kali
  const showGate = $derived(router.current !== 'monitoring' && gate.kind !== 'offline' && gate.kind !== 'no-camera')
  let open = $state(false)

  function onWindowClick(e: MouseEvent) {
    if (open && !(e.target as Element).closest('.system')) open = false
  }
  function onKeydown(e: KeyboardEvent) {
    if (open && e.key === 'Escape') open = false
  }
</script>

<svelte:window onclick={onWindowClick} onkeydown={onKeydown} />

<header class="topbar">
  <div class="brand" title={BRAND.full}>
    <ShieldCheck size={22} strokeWidth={2} aria-hidden="true" />
    <span class="brand-text">
      <span class="brand-name">{BRAND.name}</span>
      <span class="brand-tagline">{BRAND.tagline}</span>
    </span>
  </div>

  {#if session.authenticated && !session.setupRequired}
    <nav aria-label={NAV.label}>
      {#each ROUTES as route (route)}
        <a href={href(route)} aria-current={router.current === route ? 'page' : undefined}>{NAV[route]}</a>
      {/each}
    </nav>
  {/if}

  <div class="status">
    {#if showGate}
      <a class="gate tone-{gate.tone}" href={href('monitoring')} title={GATE_CHIP.title}>
        <span class="dot"></span>
        <span class="label">{GATE_CHIP.text(gate.title, gate.trackId)}</span>
      </a>
    {/if}

    {#if connection === 'signed_out'}
      <span class="chip" title={CONNECTION.signedOut}
        ><LogIn size={14} aria-hidden="true" /> <span class="label">{CONNECTION.signedOut}</span></span
      >
    {:else if connection === 'disconnected'}
      <span class="chip tone-danger" title={CONNECTION.lost}
        ><WifiOff size={14} aria-hidden="true" /> <span class="label">{CONNECTION.lost}</span></span
      >
    {:else}
      <div class="system">
        <button
          type="button"
          class="chip summary tone-{summary.tone}"
          aria-expanded={open}
          aria-haspopup="true"
          title={chipTitle(summary.text, SYSTEM_STATUS.open)}
          onclick={() => (open = !open)}
        >
          <span class="dot"></span><span class="label">{summary.text}</span><ChevronDown size={14} aria-hidden="true" />
        </button>
        {#if open}
          <div class="panel" role="dialog" aria-label={SYSTEM_STATUS.title}>
            <p class="panel-title">{SYSTEM_STATUS.title}</p>
            <ul>
              {#each items as item, i (i)}
                {@const Icon = item.icon}
                <li class="tone-{item.tone}">
                  <Icon size={16} aria-hidden="true" />
                  <span
                    ><span class="item-text">{item.text}</span>{#if item.hint}<span class="item-hint">{item.hint}</span
                      >{/if}</span
                  >
                </li>
              {/each}
            </ul>
          </div>
        {/if}
      </div>
    {/if}
    {#if session.authenticated}
      <span class="chip tone-ok" title={AUTH.accounts}>
        <User size={14} aria-hidden="true" />
        <span class="label">{session.user?.username || 'admin'}</span>
      </span>
      <button class="key" onclick={() => session.logout()} title={LOGIN.logoutBtn} aria-label={LOGIN.logoutBtn}>
        <LogOut size={16} aria-hidden="true" />
      </button>
    {/if}
    <span class="clock mono">{now.toLocaleTimeString(CLOCK.locale, { hour12: false })}</span>
  </div>
</header>

<style>
  .topbar {
    height: var(--topbar-h);
    display: flex;
    align-items: center;
    gap: var(--space-4);
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
  .brand-name {
    font-weight: 700;
    font-size: var(--text-md);
    letter-spacing: 0.32em;
  }
  .brand-tagline {
    font-size: 0.625rem;
    color: var(--text-muted);
    letter-spacing: 0.06em;
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
  .status {
    margin-left: auto;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-sm);
  }
  .chip,
  .gate {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 8px;
    border-radius: 999px;
    border: 1px solid var(--border);
    color: var(--text-muted);
    white-space: nowrap;
    flex-shrink: 0;
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
  .system {
    position: relative;
    flex-shrink: 1;
    min-width: 0;
  }
  .summary {
    max-width: 100%;
    background: transparent;
    cursor: pointer;
    font-weight: 600;
  }
  .summary:hover {
    background: var(--surface-2);
  }
  .summary.tone-ok .dot {
    background: var(--ok);
  }
  .summary.tone-warn .dot {
    background: var(--warn);
  }
  .summary.tone-danger .dot {
    background: var(--danger);
  }
  .panel {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    z-index: 40;
    width: 320px;
    padding: var(--space-3);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px var(--backdrop);
  }
  .panel-title {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: 600;
  }
  .panel ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .panel li {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    padding: var(--space-2) 0;
    border-top: 1px solid var(--border);
    color: var(--text-muted);
  }
  .panel li :global(svg) {
    flex-shrink: 0;
    margin-top: 2px;
  }
  .item-text {
    display: block;
    color: var(--text);
  }
  .panel li.tone-warn .item-text {
    color: var(--warn);
  }
  .panel li.tone-danger .item-text {
    color: var(--danger);
  }
  .item-hint {
    display: block;
    font-size: var(--text-xs);
    color: var(--text-muted);
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
    padding-left: var(--space-1);
    flex-shrink: 0;
  }

  @media (max-width: 1280px) {
    .brand-tagline {
      display: none;
    }
  }
  @media (max-width: 1150px) {
    .topbar {
      gap: var(--space-3);
      padding: 0 var(--space-4);
    }
    .clock {
      display: none;
    }
  }
  @media (max-width: 1024px) {
    .chip .label {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }
    .chip {
      padding: 4px 6px;
    }
  }
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
