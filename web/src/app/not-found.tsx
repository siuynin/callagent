import Link from "next/link";

// Rendered inside the workspace <main> for unknown slugs, so no <main> wrapper here.
export default function NotFound() {
  return (
    <div className="pagehead">
      <div>
        <div className="eyebrow">VOICE AGENT WORKSPACE</div>
        <h1>Không tìm thấy trang</h1>
        <p>
          Trang này chưa có hoặc đã được chuyển. <Link className="link" href="/">Về Tổng quan</Link>
        </p>
      </div>
    </div>
  );
}
