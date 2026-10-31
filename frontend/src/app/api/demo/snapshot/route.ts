import { getSnapshot, scenarioSchema } from "@/lib/demo";
import { NextResponse } from "next/server";

export function GET(request: Request) {
    const scenario = scenarioSchema.safeParse(new URL(request.url).searchParams.get("scenario") ?? "healthy");
    if (!scenario.success) return NextResponse.json({ error: "Kịch bản không hợp lệ." }, { status: 400 });
    return NextResponse.json(getSnapshot(scenario.data), { headers: { "Cache-Control": "no-store" } });
}
