// ---------- HUD ----------
// Numbers read the NEWEST state frame (never an interpolated pose);
// per-frame state that is purely HUD-side (grade banner, replay
// markers, heartbeat pacing) lives here.
import type { LineViewer } from './lineSensor';
import type { SimState, TrackData } from './protocol';

export const el = (id: string) => document.getElementById(id)!;

export const hudState = {
  lastGrade: null as any,            // race run verdict, cleared on task/reset
  replayX: null as number | null,    // cache playback speed, null = live
  recLive: false,                    // mission running -> the replay row
                                     // offers catch-up instead of playback
};
let recLabelLive: boolean | null = null;  // label state, to touch DOM on flip only

export function applyHudState(st: SimState) {
  hudState.lastGrade = st.grade ?? null;
  hudState.replayX = st.replay?.x ?? null;
  hudState.recLive = st.rec?.live ?? false;
}

export function setConn(live: boolean) {
  const dot = el('hud-conn');
  dot.textContent = live ? '●' : '○';
  dot.className = live ? 'conn-live' : 'conn-down';
}

export function buildTaskButtons(trackData: TrackData, sendCmd: (obj: unknown) => void) {
  const wrap = el('task-btns');
  wrap.textContent = '';
  for (const id of Object.keys(trackData.tasks).sort((a, b) => Number(a) - Number(b))) {
    const b = document.createElement('button');
    b.textContent = `${id} ${trackData.tasks[id].title}`;
    b.dataset.task = id;
    // no `turbo` key: the server keeps its own default per task
    b.onclick = () => sendCmd({ type: 'task', task: Number(id) });
    wrap.appendChild(b);
  }
  const rep = el('replay-btns');
  rep.textContent = '';
  for (const x of [1, 2, 4, 8]) {
    const b = document.createElement('button');
    b.textContent = `回放×${x}`;
    b.dataset.x = String(x);
    b.onclick = () => sendCmd({ type: 'replay', x });
    rep.appendChild(b);
  }
  const live = document.createElement('button');
  live.textContent = '直播';
  live.dataset.x = '0';
  live.onclick = () => sendCmd({ type: 'live' });
  rep.appendChild(live);
  recLabelLive = null;   // force the label refresh on the next frame
}

function refreshReplayLabels() {
  if (recLabelLive === hudState.recLive) return;
  recLabelLive = hudState.recLive;
  document.querySelectorAll('#replay-btns button').forEach((b) => {
    const x = Number((b as HTMLElement).dataset.x);
    b.textContent = x === 0 ? '直播' : `${hudState.recLive ? '追看' : '回放'}×${x}`;
  });
}

const PHASE_ZH: Record<string, string> = { arm: 'Arm', run: 'Run', brake: 'Brake', done: 'Done' };
let prevFw: { seq: number; t: number } | null = null;

export function updateHUD(deps: {
  simLive: boolean; lastState: SimState | null;
  app: 'twin' | 'race' | null; lineViewer: LineViewer;
}) {
  if (!deps.simLive || !deps.lastState) {
    deps.lineViewer.update(undefined, undefined, undefined);
    el('hud-mode').textContent = 'offline (waiting for sim server)';
    el('hud-note').textContent = 'Static mode: explode / hover available';
    return;
  }
  const st = deps.lastState;
  el('btn-pause').textContent = st.paused ? 'Run' : 'Pause';
  const m = deps.app === 'race' ? st.mission : undefined;
  deps.lineViewer.update(st.line, m?.e_lat_mm, m?.line_source);
  if (m) {
    const phase = PHASE_ZH[m.phase] ?? m.phase;
    el('hud-mode').textContent =
      `Task ${m.task} ${phase} ${m.seg} ${m.lap}/${m.laps}` + (st.paused ? ' — paused' : '');
    el('hud-time').textContent = m.elapsed != null ? `${m.elapsed.toFixed(1)} s` : `${st.t.toFixed(1)} s`;
    document.querySelectorAll('#task-btns button').forEach((b) =>
      b.classList.toggle('active', Number((b as HTMLElement).dataset.task) === m.task));
  } else {
    el('hud-mode').textContent = st.paused ? `${st.mode ?? '…'} — paused` : `${st.mode ?? '…'}`;
    el('hud-time').textContent = `${st.t.toFixed(1)} s`;
  }
  const banner = el('grade-banner');
  if (deps.app === 'race' && hudState.lastGrade) {
    const g = hudState.lastGrade;
    const limit = g.limit_s != null ? ` / ${g.limit_s.toFixed(0)}s` : '';
    const detail =
      `${(g.elapsed_s ?? 0).toFixed(1)}s${limit} · 停车 ${(g.stop_dist_m * 100).toFixed(0)}cm · ${g.nodes.length} 节点`;
    banner.textContent = g.pass ? `任务 ${g.task} ✅ 满分 ${detail}`
                                : `任务 ${g.task} ❌ 未过 ${detail}`;
    banner.className = 'hud-row grade ' + (g.pass ? 'grade-pass' : 'grade-fail');
  } else {
    banner.className = 'hud-row grade hidden';
  }
  // replay controls: offered as soon as the server reports a recording
  // (also mid-run: xN plays catch-up over the recorded prefix and hands
  // back to live at the live edge; 直播 = jump to the live edge)
  const repRow = el('replay-btns');
  if (deps.app === 'race' && st.rec && st.rec.n > 1) {
    repRow.classList.remove('hidden');
    refreshReplayLabels();
    document.querySelectorAll('#replay-btns button').forEach((b) =>
      b.classList.toggle('active', Number((b as HTMLElement).dataset.x) === hudState.replayX));
  } else {
    repRow.classList.add('hidden');
  }
  // one speed slot, one semantics: travel-axis speed (bot/telemetry.py)
  el('hud-speed').textContent = `${(st.speed_mps * 100).toFixed(1)} cm/s`;
  // fields both backends emit
  el('hud-tilt').textContent = `${st.tilt_deg.toFixed(2)}°`;
  el('hud-y').textContent = `${(st.pos[1] * 100).toFixed(1)} cm`;
  el('hud-duty').textContent = `${(st.duty[0] / 10).toFixed(0)}% / ${(st.duty[1] / 10).toFixed(0)}%`;
  el('hud-enc').textContent = `${st.enc[0]} / ${st.enc[1]}`;
  el('hud-batt').textContent = `${st.batt_v.toFixed(1)} V`;
  const fwEl = el('hud-fw');
  const fw = st.fw_seq;                 // firmware heartbeat, either backend
  if (typeof fw === 'number') {
    let hz = '';
    if (prevFw && fw >= prevFw.seq && st.t > prevFw.t) {
      hz = ` @ ${((fw - prevFw.seq) / (st.t - prevFw.t)).toFixed(0)} Hz`;
    }
    prevFw = { seq: fw, t: st.t };
    fwEl.textContent = `♥ ${fw}${hz}`;
  } else {
    prevFw = null;
    fwEl.textContent = '—';
  }
  el('hud-note').textContent = st.fallen ? 'Fallen (motors cut)' : 'Sim-driven: explode locked';
}
