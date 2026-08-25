# Who Gets You? — bản Next.js (setup)

Phiên bản viết lại: **Next.js + Supabase**, realtime bằng websocket (không còn polling).

## Cần làm 3 bước để chạy

### 1. Tạo bảng dữ liệu trong Supabase

- Vào Supabase Dashboard → dự án của bạn → **SQL Editor** → **New query**.
- Copy toàn bộ nội dung file [`supabase/schema.sql`](supabase/schema.sql) vào và bấm **Run**.
- Chạy lại được nhiều lần (nó tự xoá & tạo lại các bảng của game).

### 2. Điền khoá vào `web/.env.local`

- Copy file mẫu: `cp .env.local.example .env.local`
- Lấy giá trị trong Supabase → **Project Settings**:
  - `NEXT_PUBLIC_SUPABASE_URL` → mục **Data API** → *Project URL*
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY` → mục **API Keys** → *anon / public* (hoặc *Publishable key*)
  - `SUPABASE_SERVICE_ROLE_KEY` → mục **API Keys** → *service_role* (khoá bí mật — chỉ dùng ở server)
- Điền thêm `GOOGLE_API_KEY` (dùng model Gemini mặc định) — phần này cần cho Phase 3 trở đi, chưa cần ngay để test lobby.

> File `.env.local` đã được `.gitignore` nên khoá không bao giờ bị đẩy lên git.

### 3. Chạy

```bash
cd web
npm run dev
```

Mở http://localhost:3000. Để thử realtime: mở **2–3 tab** (hoặc điện thoại cùng wifi vào `http://<IP-máy>:3000`), một tab tạo phòng, các tab kia vào bằng mã. Người vào là mọi tab thấy ngay — **không còn refresh 3 giây**.

## Deploy lên Vercel

- Import repo, đặt **Root Directory = `web`**.
- Thêm 4 biến môi trường ở Project → Settings → Environment Variables (giống `.env.local`).
- Deploy.

## Đã xong (Phase 0–1)

- Trang chủ, tạo phòng, vào phòng
- Lobby realtime: danh sách người chơi cập nhật trực tiếp, chủ phòng chỉnh điểm thắng / xoá người / bắt đầu
- Nền dữ liệu Supabase + subscription websocket

## Kế tiếp (Phase 2–4)

- Màn chơi đầy đủ 7 phase, sinh câu hỏi bằng AI, tính điểm.
