"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getSupabaseBrowser } from "@/lib/supabase/client";
import type { Guess, Player, Room, Round, Submission } from "@/lib/types";

export interface UseGameResult {
  room: Room | null;
  players: Player[];
  round: Round | null;
  submissions: Submission[];
  guesses: Guess[];
  live: boolean;
  loading: boolean;
  refetch: () => Promise<void>;
}

/**
 * Realtime view of a whole game: room + players + the current round's
 * submissions and guesses. Any Postgres change is pushed over websocket.
 */
export function useGame(code: string): UseGameResult {
  const [room, setRoom] = useState<Room | null>(null);
  const [players, setPlayers] = useState<Player[]>([]);
  const [round, setRound] = useState<Round | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [guesses, setGuesses] = useState<Guess[]>([]);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const roomIdRef = useRef<string | null>(null);

  const refetch = useCallback(async () => {
    const supabase = getSupabaseBrowser();
    const { data: roomRow } = await supabase
      .from("rooms")
      .select("*")
      .eq("code", code.toUpperCase())
      .maybeSingle();
    if (!roomRow) {
      setRoom(null);
      setLoading(false);
      return;
    }
    roomIdRef.current = roomRow.id;
    setRoom(roomRow as Room);

    const [{ data: playerRows }, { data: roundRow }] = await Promise.all([
      supabase.from("players").select("*").eq("room_id", roomRow.id).order("joined_at", { ascending: true }),
      supabase
        .from("rounds")
        .select("*")
        .eq("room_id", roomRow.id)
        .eq("round_no", roomRow.round)
        .maybeSingle(),
    ]);
    setPlayers((playerRows ?? []) as Player[]);
    setRound((roundRow ?? null) as Round | null);

    if (roundRow) {
      const [{ data: subRows }, { data: guessRows }] = await Promise.all([
        supabase.from("submissions").select("*").eq("round_id", roundRow.id),
        supabase.from("guesses").select("*").eq("round_id", roundRow.id),
      ]);
      setSubmissions((subRows ?? []) as Submission[]);
      setGuesses((guessRows ?? []) as Guess[]);
    } else {
      setSubmissions([]);
      setGuesses([]);
    }
    setLoading(false);
  }, [code]);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refetch();

    const supabase = getSupabaseBrowser();
    const onChange = () => {
      if (!cancelled) void refetch();
    };
    const channel = supabase
      .channel(`game:${code.toUpperCase()}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "rooms", filter: `code=eq.${code.toUpperCase()}` }, onChange)
      .on("postgres_changes", { event: "*", schema: "public", table: "players" }, onChange)
      .on("postgres_changes", { event: "*", schema: "public", table: "rounds" }, onChange)
      .on("postgres_changes", { event: "*", schema: "public", table: "submissions" }, onChange)
      .on("postgres_changes", { event: "*", schema: "public", table: "guesses" }, onChange)
      .subscribe((s) => {
        if (cancelled) return;
        const subscribed = s === "SUBSCRIBED";
        setLive(subscribed);
        // On (re)connect, refetch to catch anything missed while disconnected.
        if (subscribed) void refetch();
      });

    // Refetch when the tab regains focus (mobile sleep / background).
    const onVisible = () => {
      if (!cancelled && document.visibilityState === "visible") void refetch();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      void supabase.removeChannel(channel);
    };
  }, [code, refetch]);

  return { room, players, round, submissions, guesses, live, loading, refetch };
}
