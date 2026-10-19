import type { Metadata } from "next";
import { Suspense } from "react";

export const metadata: Metadata = { title: "Đăng nhập" };

async function LoginButton({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const returnTo = typeof sp.returnTo === "string" ? sp.returnTo : "/";
  return (
    <a className="btn primary" style={{ display: "block", textAlign: "center" }} href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}>
      Đăng nhập bằng tài khoản công ty
    </a>
  );
}

export default function LoginPage({ searchParams }: PageProps<"/dang-nhap">) {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 16, background: "var(--bg)" }}>
      <section className="card pad" style={{ width: "100%", maxWidth: 400 }}>
        <div className="logo" style={{ padding: 0, marginBottom: 22 }}>
          <span className="mark">≋</span>VoiceOS
        </div>
        <h1 style={{ fontSize: 22 }}>Đăng nhập</h1>
        <p style={{ margin: "6px 0 22px" }}>Dùng tài khoản đã được quản trị viên mời vào workspace.</p>
        <Suspense fallback={<span className="btn primary">Đăng nhập</span>}>
          <LoginButton searchParams={searchParams} />
        </Suspense>
        <p className="small" style={{ marginTop: 16 }}>
          Chưa có quyền truy cập? Liên hệ quản trị viên workspace của bạn.
        </p>
      </section>
    </div>
  );
}
