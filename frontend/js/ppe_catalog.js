/**
 * ===================================================================
 * SAFEGUARD AI - Katalog APD
 * Satu-satunya tempat frontend mengetahui item APD apa saja yang ada.
 * Isinya datang dari `GET /api/ppe-rules`, yang dibangkitkan dari
 * `backend/ppe_rules.py`; tidak ada nama item yang ditulis tetap di sini.
 * ===================================================================
 */

let catalogPromise = null;

/** Memuat katalog sekali; pemanggil berikutnya memakai hasil yang sama. */
export function loadCatalog(url) {
  if (!catalogPromise) {
    catalogPromise = fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => data.items || [])
      .catch((err) => {
        // Jangan simpan kegagalan, supaya pemanggilan berikutnya mencoba lagi
        catalogPromise = null;
        throw err;
      });
  }
  return catalogPromise;
}

/** Mengganti katalog tersimpan, mis. setelah operator menghidupkan/mematikan item. */
export function replaceCatalog(items) {
  catalogPromise = Promise.resolve(items);
}

/** Item yang sedang diperiksa (dihidupkan operator). */
export function activeItems(items) {
  return items.filter((item) => item.required);
}

/**
 * Penilaian satu item: { ok, text }.
 *
 * Aturannya cermin `PPEItem.is_satisfied` di backend: item harus terdeteksi,
 * dan bila punya syarat tambahan (qualifier), field syarat itu harus true.
 * `ok` bernilai null bila item tidak dinilai sama sekali — mis. item yang
 * ditambahkan ke katalog setelah sebuah catatan lama dibuat.
 */
export function assessItem(item, result) {
  if (!result) {
    return { ok: null, text: 'Tidak dinilai' };
  }
  const qualifier = item.qualifier;
  const qualifierOk = qualifier ? Boolean(result[qualifier.key]) : true;

  if (result.detected && qualifierOk) {
    const color = item.reports_color ? result.color : '';
    return { ok: true, text: color || item.ok_label };
  }
  if (result.detected && qualifier) {
    return { ok: false, text: qualifier.fail_label };
  }
  return { ok: false, text: item.fail_label };
}
