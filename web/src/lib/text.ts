/** Accent-insensitive Vietnamese matching: "khach" finds "Khách", "duong" finds "Đường". */
export function fold(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
}
