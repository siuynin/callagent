import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

export const metadata: Metadata = { title: "Không vào được workspace" };

const REASONS: Record<string, string> = {
  NOT_INVITED: "Tài khoản này chưa được mời vào workspace nào. Nhờ quản trị viên mời đúng email bạn dùng để đăng nhập.",
  EMAIL_NOT_VERIFIED: "Nhà cung cấp đăng nhập chưa xác minh email của tài khoản này.",
  IDENTITY_MISMATCH: "Email này đã gắn với một tài khoản đăng nhập khác. Liên hệ quản trị viên.",
  NO_MEMBERSHIP: "Tài khoản không còn thuộc workspace nào.",
  STATE_MISMATCH: "Phiên đăng nhập không hợp lệ hoặc đã quá hạn. Thử đăng nhập lại.",
  NONCE_MISMATCH: "Phản hồi đăng nhập không khớp yêu cầu. Thử đăng nhập lại.",
  TOKEN_EXCHANGE: "Không hoàn tất được đăng nhập với nhà cung cấp. Thử lại sau.",
  PROVIDER_ERROR: "Nhà cung cấp đăng nhập từ chối yêu cầu.",
  INVALID_TOKEN: "Không xác thực được phản hồi của nhà cung cấp đăng nhập. Thử lại sau ít phút.",
  TOKEN_EXPIRED: "Phiên đăng nhập đã hết hạn. Thử đăng nhập lại.",
  OIDC_UNAVAILABLE: "Tạm thời không liên lạc được nhà cung cấp đăng nhập. Thử lại sau.",
};

async function Reason({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const code = typeof sp.reason === "string" ? sp.reason : "";
  return <p style={{ margin: "6px 0 22px" }}>{REASONS[code] ?? "Không đăng nhập được vào workspace."}</p>;
}

export default function NotInvitedPage({ searchParams }: PageProps<"/chua-duoc-moi">) {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 16, background: "var(--bg)" }}>
      <section className="card pad" style={{ width: "100%", maxWidth: 440 }}>
        <h1 style={{ fontSize: 22 }}>Không vào được workspace</h1>
        <Suspense fallback={<p>…</p>}>
          <Reason searchParams={searchParams} />
        </Suspense>
        <Link className="btn" href="/dang-nhap">
          Thử đăng nhập lại
        </Link>
      </section>
    </div>
  );
}
