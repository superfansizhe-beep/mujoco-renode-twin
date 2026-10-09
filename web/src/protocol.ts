// ---------- State protocol ----------
// One viewer, two backends: the balance twin (:8765) and the race loop
// (:8766 via ?ws=, or bot.ws() from the console). Two frame kinds:
//   scene  the server's first message per connection (bot/server.py) --
//          its identity (app) plus static scene data; race embeds the
//          whole track payload (race/scene.py). Owns the UI mode.
//   state  base fields built by bot/telemetry.py -- the single schema
//          source; each backend adds its identity field (twin `mode`,
//          race `mission`). speed_mps is speed along the bot's travel
//          axis, positive nose-first (twin leads chassis +Y, race runs
//          bar-first = -Y).
import type { LineConfig, LineState } from './lineSensor';

export interface SimState {
  type: 'state';
  t: number;
  pos: number[];
  quat_xyzw: number[];
  wheel_deg: number[];
  tilt_deg: number;
  speed_mps: number;      // base field: travel-axis speed, both backends
  duty: number[];          // permille, [left, right]
  enc: number[];
  batt_v: number;
  paused: boolean;
  grade?: any;               // race run verdict (server pushes it on finish)
  replay?: { x: number; i: number; n: number };  // cache playback marker
  rec?: { n: number; live: boolean };  // cache size + mission-running flag
  fallen: boolean;
  mode?: string;           // twin identity
  fw_seq?: number | null;  // firmware heartbeat, null/absent on stubs
  line?: LineState;
  mission?: {
    task: number; phase: string; seg: string;
    lap: number; laps: number;
    elapsed: number | null; e_lat_mm: number;
    line_source?: string;
  };
}

export interface SceneMsg {
  type: 'scene';
  app: 'twin' | 'race';
  title: string;
  track?: TrackData;
}

// ---------- Race mode: track payload ----------
// Track truth rides the scene frame (race/scene.py builds it from the
// same race.track/race.tasks the backend grades against) -- nothing to
// regenerate by hand. Frame is CAD (z up, origin at field lower-left);
// the field floor z_cad = 0 coincides with the bot's feet.
export interface TrackData {
  field: [number, number];
  tape_half: number;
  tapes: { name: string; poly: [number, number][];
    center: [number, number]; radius: number; start: number; sweep: number }[];
  ghosts: { name: string; poly: [number, number][] }[];
  tasks: Record<string, { title: string }>;
  line_array?: LineConfig;
}

// Narrow check at the boundary: everything downstream (pose math, HUD)
// trusts these fields, so a frame missing them is dropped here rather
// than throwing inside the render loop and freezing the scene.
export function validState(st: any): st is SimState {
  const nums = (a: unknown, n: number) =>
    Array.isArray(a) && a.length === n && a.every((v) => typeof v === 'number');
  return st?.type === 'state'
    && nums(st.pos, 3) && nums(st.quat_xyzw, 4) && nums(st.wheel_deg, 2)
    && typeof st.speed_mps === 'number';
}
