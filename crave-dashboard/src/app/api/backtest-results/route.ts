/**
 * CRAVE — /api/backtest-results
 * ================================
 * Returns ML backtest status + results to the dashboard.
 * Reads from:
 *   1. Supabase (if configured) — live results pushed by backtest_runner.py
 *   2. /data/backtest_status.json — local fallback (file polling)
 *
 * GET /api/backtest-results         — latest results
 * GET /api/backtest-results?run=all — all historical runs
 * POST /api/backtest-results        — trigger a new backtest run (via subprocess)
 */

import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const SUPABASE_URL  = process.env.NEXT_PUBLIC_SUPABASE_URL  || "";
const SUPABASE_KEY  = process.env.SUPABASE_SERVICE_ROLE_KEY ||
                      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

const CRAVE_ROOT    = process.env.CRAVE_ROOT || "D:\\CRAVE";
const STATUS_FILE   = join(CRAVE_ROOT, "data", "backtest_status.json");

// ── Supabase client (optional) ─────────────────────────────────────────────
function getSupabase() {
  if (!SUPABASE_URL || !SUPABASE_KEY || SUPABASE_URL.includes("YOUR_PROJECT")) {
    return null;
  }
  return createClient(SUPABASE_URL, SUPABASE_KEY);
}

// ── Read local status file (fallback when Supabase not configured) ─────────
function readLocalStatus() {
  try {
    if (!existsSync(STATUS_FILE)) {
      return { status: "idle", progress: 0, message: "No backtest run yet", results: [] };
    }
    const raw = readFileSync(STATUS_FILE, "utf-8");
    return JSON.parse(raw);
  } catch {
    return { status: "error", progress: 0, message: "Could not read status file", results: [] };
  }
}

// ── GET ────────────────────────────────────────────────────────────────────
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const mode = searchParams.get("run") || "latest";

  // Try Supabase first
  const sb = getSupabase();
  if (sb) {
    try {
      let query = sb
        .from("ml_backtest_results")
        .select("*")
        .order("created_at", { ascending: false });

      if (mode !== "all") {
        // Latest run only (group by run_id of most recent row)
        const { data: latest } = await sb
          .from("ml_backtest_results")
          .select("run_id")
          .order("created_at", { ascending: false })
          .limit(1)
          .single();

        if (latest?.run_id) {
          query = query.eq("run_id", latest.run_id);
        }
      } else {
        query = query.limit(100);
      }

      const { data, error } = await query;

      if (!error && data && data.length > 0) {
        // Also get current status from local file
        const localStatus = readLocalStatus();
        return NextResponse.json({
          source:  "supabase",
          status:  localStatus.status,
          progress: localStatus.progress,
          message: localStatus.message,
          updated_at: localStatus.updated_at,
          results: data,
        });
      }
    } catch (e) {
      console.error("Supabase fetch error:", e);
    }
  }

  // Fallback: local status file
  const local = readLocalStatus();
  return NextResponse.json({ source: "local", ...local });
}

// ── POST — trigger a new backtest run ─────────────────────────────────────
export async function POST() {
  try {
    const { exec } = await import("child_process");
    const script = join(
      CRAVE_ROOT,
      "Sub_Projects", "Trading", "ml", "backtest_runner.py"
    );

    // Spawn detached — returns immediately, runs in background
    exec(
      `python "${script}" --background`,
      { detached: true, windowsHide: true },
      (err) => {
        if (err) console.error("Backtest spawn error:", err);
      }
    );

    return NextResponse.json({
      ok:      true,
      message: "Backtest started in background. Poll /api/backtest-results for progress.",
    });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}
