import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "healthy",
    service: "slidein-app",
    version: "1.0.0",
  });
}
