"use client";

import { use } from "react";
import Lobby from "@/components/Lobby";

export default function RoomPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  return <Lobby code={code.toUpperCase()} />;
}
