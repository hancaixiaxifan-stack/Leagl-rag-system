import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  return proxy(request, params, "GET");
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  return proxy(request, params, "POST");
}

async function proxy(
  request: NextRequest,
  paramsPromise: Promise<{ path?: string[] }>,
  method: string
) {
  const { path = [] } = await paramsPromise;
  const targetPath = path.join("/");
  const targetUrl = new URL(targetPath, API_BASE);

  request.nextUrl.searchParams.forEach((value, key) => {
    targetUrl.searchParams.set(key, value);
  });

  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    let body: string | undefined;
    if (method === "POST") {
      body = await request.text();
    }

    const response = await fetch(targetUrl.toString(), {
      method,
      headers,
      body,
    });

    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "API Proxy Error",
        detail: error instanceof Error ? error.message : String(error),
        suggestion: "请确认 FastAPI 服务是否已启动 (python -m scripts.serve)",
      },
      { status: 502 }
    );
  }
}
