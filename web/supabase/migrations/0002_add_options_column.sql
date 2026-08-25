-- Thêm cột `options` cho bảng rounds (lưu thứ tự đáp án khi đoán).
-- Chạy trong Supabase → SQL Editor. Không mất dữ liệu.
alter table rounds add column if not exists options jsonb;
