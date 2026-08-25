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
<!-- - Điền thêm `GOOGLE_API_KEY` (dùng model Gemini mặc định) — phần này cần cho Phase 3 trở đi, chưa cần ngay để test lobby. -->

> File `.env.local` đã được `.gitignore` nên khoá không bao giờ bị đẩy lên git.

### 3. Chạy

```bash
cd web
npm run dev
```

Mở http://localhost:3000. Để thử realtime: mở **2–3 tab** (hoặc điện thoại cùng wifi vào `http://<IP-máy>:3000`), một tab tạo phòng, các tab kia vào bằng mã. Người vào là mọi tab thấy ngay — **không còn refresh 3 giây**.

## Deploy lên Vercel (từng bước)

1. **Đẩy code lên GitHub**: commit + push nhánh này (`refactor_JS_deploy`) lên `dzngo/whogetsyou`.
2. Vào [vercel.com/new](https://vercel.com/new) → **Import** repo `whogetsyou`.
3. Ở màn hình cấu hình:
   - **Root Directory**: bấm *Edit* và chọn **`web`** (rất quan trọng — code Next.js nằm trong `web/`).
   - Framework: Vercel tự nhận **Next.js** (không cần chỉnh).
4. Mở **Environment Variables** và thêm 4 biến (lấy y như trong `.env.local`):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `GOOGLE_API_KEY`
5. Bấm **Deploy**. Xong sẽ có link dạng `https://whogetsyou-xxxx.vercel.app`.
6. Mỗi lần push code mới lên nhánh này, Vercel tự deploy lại.

> Supabase không cần cấu hình thêm gì cho Vercel — anon key hoạt động từ mọi tên miền, realtime chạy qua websocket bình thường.

## Đã xong (Phase 0–5)

- **Vào chơi**: trang chủ, tạo phòng, vào phòng, lobby realtime
- **Chơi**: máy trạng thái 7 phase, tự chuyển khi mọi người nộp/đoán xong
- **AI**: sinh câu hỏi theo chủ đề/mức độ, dịch sang ngôn ngữ phòng, gợi ý câu trả lời (model mặc định `gemini-3.6-flash`)
- **Điểm**: hệ số nhẹ×1/sâu×2 + decoy bonus, màn lật bài, kết quả cuối
- **Chắc chắn**: tự đồng bộ lại khi mất kết nối / quay lại tab, vào lại phòng giữa ván, chủ phòng có nút **Kết thúc sớm** và **Bỏ qua lượt**

## Kiểm thử (chạy trong `web/`)

- `node scripts/test-scoring.ts` — luật tính điểm
- `node scripts/test-flow.mjs` — một vòng chơi trên Supabase thật
- `node scripts/test-llm.mjs` — sinh câu hỏi + dịch bằng Gemini thật
