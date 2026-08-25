"use client";

import { use } from "react";
import RoomView from "@/components/RoomView";

export default function RoomPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  return <RoomView code={code.toUpperCase()} />;
}
