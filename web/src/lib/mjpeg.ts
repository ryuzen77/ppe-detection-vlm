/**
 * Aksi Svelte untuk <img> aliran MJPEG: memutus koneksi saat elemen DILEPAS dari DOM.
 *
 * Browser tidak selalu membatalkan unduhan multipart saat <img> dihapus, jadi tiap kali
 * kamera putus-sambung (blok {#if} melepas & memasang ulang <img>) satu koneksi tertinggal.
 * Setelah ±6 koneksi, batas HTTP/1.1 per host habis dan semua panggilan API dashboard
 * tertahan (temuan uji UI 24-10). Mengosongkan src memutus koneksinya.
 */
export function releaseStream(node: { src: string }) {
  return {
    destroy() {
      node.src = ''
    },
  }
}
