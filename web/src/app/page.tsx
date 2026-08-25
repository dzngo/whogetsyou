import Link from "next/link";
import { PageShell, Card } from "@/components/ui";

export default function Home() {
  return (
    <PageShell>
      <div className="flex-1 flex flex-col justify-center gap-8 py-6">
        <header className="text-center flex flex-col items-center gap-4">
          <span className="text-5xl">🎭</span>
          <h1 className="font-display font-semibold text-ink text-4xl leading-tight tracking-tight text-balance">
            Who Gets You?
          </h1>
          <p className="text-ink-soft text-[1.02rem] max-w-xs">
            Trò chơi xem bạn bè “hiểu” nhau đến mức nào. Trả lời, đoán, và cười.
          </p>
        </header>

        <div className="flex flex-col gap-3">
          <Link
            href="/host"
            className="w-full text-center bg-accent text-white font-semibold rounded-xl px-5 py-4 text-base no-underline hover:brightness-110 transition"
          >
            Tạo phòng
          </Link>
          <Link
            href="/join"
            className="w-full text-center bg-surface-2 text-ink border border-border-strong font-semibold rounded-xl px-5 py-4 text-base no-underline hover:border-accent transition"
          >
            Vào phòng
          </Link>
        </div>

        <Card className="!p-4">
          <details className="group">
            <summary className="cursor-pointer list-none flex items-center justify-between text-sm font-semibold text-ink">
              Luật chơi nhanh
              <span className="text-ink-faint group-open:rotate-180 transition-transform">⌄</span>
            </summary>
            <ul className="mt-3 flex flex-col gap-2 text-sm text-ink-soft">
              <li>• Mỗi vòng có một <strong className="text-ink font-semibold">người kể chuyện</strong> chọn chủ đề &amp; câu hỏi.</li>
              <li>• Mọi người viết một câu trả lời cho cùng câu hỏi đó.</li>
              <li>• Người nghe đoán đâu là câu trả lời thật của người kể chuyện.</li>
              <li>• Đoán đúng được điểm; đủ điểm mục tiêu là thắng.</li>
            </ul>
          </details>
        </Card>
      </div>

      <footer className="text-center text-xs text-ink-faint font-mono pt-6">
        cần tối thiểu 3 người · chơi trên điện thoại hoặc máy tính
      </footer>
    </PageShell>
  );
}
