<script lang="ts">
  // Pilihan divisi & perusahaan (T79), dipakai form tambah & ubah pekerja.
  // Daftar kosong (backend lama tanpa T79a) = kolom tidak ditampilkan.
  import type { OrgEntry } from '../../lib/api/types'
  import { WORKERS_PAGE } from '../../lib/messages'

  interface Props {
    departments: OrgEntry[]
    companies: OrgEntry[]
    departmentId: number | null
    companyId: number | null
    disabled?: boolean
    idPrefix: string
  }

  let {
    departments,
    companies,
    departmentId = $bindable(),
    companyId = $bindable(),
    disabled = false,
    idPrefix,
  }: Props = $props()
</script>

{#if departments.length || companies.length}
  <div class="org-row">
    {#if departments.length}
      <div class="field">
        <label for="{idPrefix}-department">{WORKERS_PAGE.departmentLabel}</label>
        <select id="{idPrefix}-department" class="input" bind:value={departmentId} {disabled}>
          <option value={null}>{WORKERS_PAGE.fieldDepartmentNone}</option>
          {#each departments as d (d.id)}<option value={d.id}>{d.name}</option>{/each}
        </select>
      </div>
    {/if}
    {#if companies.length}
      <div class="field">
        <label for="{idPrefix}-company">{WORKERS_PAGE.companyLabel}</label>
        <select id="{idPrefix}-company" class="input" bind:value={companyId} {disabled}>
          {#each companies as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
        </select>
      </div>
    {/if}
  </div>
{/if}

<style>
  .org-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--space-3);
  }
</style>
