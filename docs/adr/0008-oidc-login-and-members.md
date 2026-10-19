# ADR 0008 · Đăng nhập OIDC và quản lý thành viên
Trạng thái: Đã chấp nhận · 19/10/2026

## Bối cảnh
Đến M0 ứng dụng chỉ có token dev. Doanh nghiệp cần đăng nhập bằng tài khoản công ty (Google Workspace, Microsoft Entra, Keycloak…), và quản trị viên phải tự mời, đổi vai trò, gỡ người mà không cần đội vận hành.

## Quyết định
- Web là BFF: `/auth/login` chạy authorization code + PKCE S256, có `state` và `nonce`, lưu trong cookie tạm (path `/auth`, 10 phút). `/auth/callback` đổi code, kiểm nonce, gọi backend `/api/v1/me` bằng ID token; được thì đặt cookie phiên httpOnly, SameSite=Lax, mã hóa AES-GCM bằng `SESSION_SECRET`, hết hạn cùng ID token. `returnTo` chỉ nhận đường dẫn nội bộ. `/auth/logout` chỉ nhận POST, xóa cookie rồi chuyển tới `end_session_endpoint` nếu nhà cung cấp có.
- Trình duyệt không bao giờ thấy token. Server component gửi ID token tới backend dưới dạng Bearer.
- Backend tự kiểm ID token (`voiceos/auth/oidc.py`): chữ ký qua JWKS của issuer, chỉ thuật toán bất đối xứng, `iss`, `aud` (= client id của web), `exp`, `iat`.
- Người dùng định danh bằng cặp (issuer, subject), unique. Lần đầu đăng nhập, nếu email đã xác minh trùng một người được mời chưa gắn danh tính thì gắn vào. Không được mời: `NOT_INVITED`; email chưa xác minh: `EMAIL_NOT_VERIFIED`; email đã gắn với danh tính khác: `IDENTITY_MISMATCH`.
- Token dev chỉ được nhận khi `APP_ENV=dev`. Web không đặt `OIDC_ISSUER` thì dùng `DEV_AUTH_TOKEN` như trước.
- `/api/v1/admin/members` (admin/owner): xem, mời, đổi vai trò, gỡ. Chỉ owner cấp hoặc gỡ quyền owner; không tự đổi hay tự gỡ mình; workspace luôn còn ít nhất một admin; gỡ ai thì việc đang mở của họ trở về chưa phân công. Màn `/cai-dat` dùng các API này; vai trò khác chỉ thấy danh bạ.
- `web/scripts/mock-oidc.mjs` là nhà cung cấp OIDC giả lập cho dev và kiểm thử, không bao giờ dùng cho production.

## Hệ quả
- Phiên dài bằng ID token (thường 1 giờ). Chưa có refresh token: hết hạn thì đăng nhập lại.
- Gỡ thành viên có hiệu lực ngay ở backend vì mỗi request kiểm membership, dù cookie phiên còn hạn.
- PyJWT không tải lại JWKS liên tục khi gặp `kid` lạ (có thời gian chờ). Nhà cung cấp xoay khóa nhiều lần trong vài chục giây sẽ làm đăng nhập lỗi tạm thời (`INVALID_TOKEN`).
- Mỗi tenant hiện dùng chung một issuer cấu hình bằng biến môi trường. Nhiều issuer theo tenant, SCIM, phân quyền theo chi nhánh để sau.
