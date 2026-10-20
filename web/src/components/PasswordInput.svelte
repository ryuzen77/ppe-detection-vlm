<script lang="ts">
  // Kolom sandi dengan tombol tampilkan/sembunyikan: sandi sering ditempel atau diketik di layar
  // sentuh gerbang, dan tanpa ini admin tidak bisa memeriksa apa yang sudah terisi.
  import { AUTH } from '../lib/messages'
  import Eye from '@lucide/svelte/icons/eye'
  import EyeOff from '@lucide/svelte/icons/eye-off'

  interface Props {
    value: string
    id?: string
    disabled?: boolean
    required?: boolean
    autocomplete?: AutoFill
    placeholder?: string
  }

  let { value = $bindable(), id, disabled = false, required = false, autocomplete, placeholder }: Props = $props()
  let shown = $state(false)
</script>

<div class="wrap">
  <input {id} class="input" type={shown ? 'text' : 'password'} bind:value {disabled} {required} {autocomplete} {placeholder}
    autocapitalize="off" spellcheck="false" />
  <button type="button" class="toggle" onclick={() => (shown = !shown)} {disabled}
    aria-label={shown ? AUTH.hidePassword : AUTH.showPassword} aria-pressed={shown}
    title={shown ? AUTH.hidePassword : AUTH.showPassword}>
    {#if shown}<EyeOff size={16} />{:else}<Eye size={16} />{/if}
  </button>
</div>

<style>
  .wrap {
    position: relative;
  }
  .wrap .input {
    width: 100%;
    padding-right: 40px;
  }
  .toggle {
    position: absolute;
    top: 50%;
    right: 4px;
    transform: translateY(-50%);
    display: inline-grid;
    place-items: center;
    width: 32px;
    height: 32px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .toggle:hover:not(:disabled) {
    color: var(--text);
  }
  .toggle:disabled {
    cursor: not-allowed;
  }
</style>
