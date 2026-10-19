import Link from "next/link";

export default function NotFound() {
  return (
    <main className="main">
      <h1>Không tìm thấy trang</h1>
      <p className="muted">Trang này chưa có hoặc đã được chuyển.</p>
      <Link href="/">Về Tổng quan</Link>
    </main>
  );
}
