import Image from "next/image";

const previews = [
  {
    title: "新版 /drift 法律漂移报告页 v3",
    src: "/generated.png",
    note: "暖白/象牙白背景，不发黄，只保留当前 drift 页面真实功能。",
    width: 1536,
    height: 1024,
    primary: true,
  },
  {
    title: "上一版 /drift 偏黄纸张风格",
    src: "/generated-drift-v2.png",
    note: "颜色偏档案黄纸，用于对比。",
    width: 1487,
    height: 1058,
    primary: false,
  },
  {
    title: "旧版 /drift 方向参考",
    src: "/generated-drift.png",
    note: "上一版结构参考。",
    width: 1487,
    height: 1058,
    primary: false,
  },
  {
    title: "/ask 法律咨询工作台参考",
    src: "/generated-ask.png",
    note: "右侧证据栏和问答工作台结构参考。",
    width: 1536,
    height: 1024,
    primary: false,
  },
];

export default function GeneratedPreviewPage() {
  return (
    <main className="min-h-screen bg-[#fbf6ea] px-6 py-8 text-[#1f2933]">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="border-b border-[#d8d0c1] pb-4">
          <p className="text-xs uppercase tracking-[0.18em] text-[#7c6f5b]">
            Generated UI Mockups
          </p>
          <h1 className="mt-2 text-2xl font-semibold">前端效果图预览</h1>
          <p className="mt-2 text-sm text-[#6b6254]">
            当前主图位于 <code>/public/generated.png</code>，可直接打开{" "}
            <code>/generated.png</code> 查看原图。
          </p>
        </header>

        <section className="grid gap-6">
          {previews.map((preview) => (
            <article
              key={preview.src}
              className="rounded-lg border border-[#d8d0c1] bg-[#fffdf8] p-4 shadow-sm"
            >
              <div className="mb-3 flex items-end justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold">{preview.title}</h2>
                    {preview.primary && (
                      <span className="rounded-full bg-[#1f3a5f] px-2 py-0.5 text-[11px] font-medium text-white">
                        最新
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-[#7c6f5b]">{preview.note}</p>
                </div>
                <a
                  href={preview.src}
                  className="rounded-md border border-[#1f3a5f] px-3 py-1.5 text-xs font-medium text-[#1f3a5f] hover:bg-[#1f3a5f] hover:text-white"
                >
                  打开原图
                </a>
              </div>
              <Image
                src={preview.src}
                alt={preview.title}
                width={preview.width}
                height={preview.height}
                priority={preview.primary}
                className="w-full rounded-md border border-[#e4dccd]"
              />
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
