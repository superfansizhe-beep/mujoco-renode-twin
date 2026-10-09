import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { LineViewer } from './lineSensor';
import { CAD_TO_THREE, robotRoot } from './frame';
import { PART_INFO, parts, nodeToEntry, cadNodes, setSensorFocus, type PartEntry } from './parts';
import { buildTrack, frameField } from './track3d';
import { pushPose, resetFollow, wheelNodes, wheelBakedQuat, applyInterpolatedPose } from './pose';
import { el, applyHudState, setConn, buildTaskButtons, updateHUD } from './hud';
import { validState, type SceneMsg, type SimState, type TrackData } from './protocol';

// ---------- Scene ----------
const canvas = document.getElementById('scene') as HTMLCanvasElement;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1d23);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.01, 10);
camera.position.set(0.35, 0.25, -0.45);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 0.08, 0);

scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dir = new THREE.DirectionalLight(0xffffff, 1.4);
dir.position.set(0.3, 0.5, 0.8);
dir.castShadow = true;
scene.add(dir);
const rim = new THREE.DirectionalLight(0x88aaff, 0.5);
rim.position.set(-0.4, -0.3, 0.3);
scene.add(rim);

const grid = new THREE.GridHelper(0.4, 20, 0x444c5c, 0x2a2f3a);
scene.add(grid);
scene.add(robotRoot);

// ---------- Viewer state ----------
let simLive = false;           // a state frame arrived in the last second
let lastState: SimState | null = null;
let app: 'twin' | 'race' | null = null;   // scene-frame identity
let prevApp: 'twin' | 'race' | null | undefined = undefined;
let sensorView = false;
let preSensorCamera: { position: THREE.Vector3; target: THREE.Vector3 } | null = null;
let raceFollow = true;
let trackData: TrackData | null = null;
let trackGroup: THREE.Object3D | null = null;   // built once, toggled
const routeGuides = new THREE.Group();
routeGuides.visible = false;

function applyState(st: any) {
  if (!validState(st)) {
    console.warn('bad state frame dropped:', st);
    return;
  }
  lastState = st;
  applyHudState(st);
  simLive = true;
  simWatchdog = performance.now();

  pushPose(st);
  if (sensorView && app === 'race' && st.line) {
    const points = st.line.spots.filter((p): p is number[] => p !== null);
    if (points.length) {
      const target = points.reduce((v, p) => v.add(new THREE.Vector3(...p as [number, number, number])),
        new THREE.Vector3()).multiplyScalar(1 / points.length);
      target.z = 0.02;
      const q = new THREE.Quaternion(st.quat_xyzw[0], st.quat_xyzw[1],
                                     st.quat_xyzw[2], st.quat_xyzw[3]);
      // View in travel direction (chassis -Y), matching the 7..0 HUD. Sensor
      // focus hides the CAD shell so it cannot obscure the floor footprints.
      camera.position.copy(target).add(new THREE.Vector3(0, 0.10, 0.30).applyQuaternion(q))
        .applyMatrix4(CAD_TO_THREE);
      // Aim just behind the footprints so the probe row remains above the
      // diagnostic panel on small displays.
      controls.target.copy(target).add(new THREE.Vector3(0, 0.05, 0).applyQuaternion(q))
        .applyMatrix4(CAD_TO_THREE);
    }
  }
}

function applyScene(msg: SceneMsg) {
  if (msg?.type !== 'scene' || (msg.app !== 'twin' && msg.app !== 'race')) return;
  app = msg.app;
  if (msg.title) document.title = msg.title;
  if (msg.track) trackData = msg.track;
  if (msg.track?.line_array) lineViewer.configure(msg.track.line_array);
  syncAppUI();
}

// The scene frame owns the UI mode, symmetrically: race shows the
// track/task buttons/field view, twin restores grid/twin buttons.
function syncAppUI() {
  const changed = app !== prevApp;
  prevApp = app;
  const race = app === 'race';
  el('app').classList.toggle('race-mode', race);
  if (!race) resetFollow();
  if (!race && sensorView) {
    sensorView = false;
    preSensorCamera = null;
    el('btn-sensor-view').classList.remove('active');
    el('btn-sensor-view').textContent = 'Sensor view';
    setSensorFocus(false);
  }
  if (race && trackData && !trackGroup) {
    trackGroup = buildTrack(trackData, routeGuides);
    scene.add(trackGroup);
  }
  if (trackGroup) trackGroup.visible = race;
  lineViewer.show(race);
  el('app').classList.toggle('sensor-focus', race && sensorView);
  el('btn-guides').classList.toggle('hidden', !race);
  el('btn-sensor-view').classList.toggle('hidden', !race);
  el('btn-follow-car').classList.toggle('hidden', !race || sensorView);
  el('btn-follow-car').classList.toggle('active', race && raceFollow);
  grid.visible = !race;
  el('twin-btns').classList.toggle('hidden', app !== 'twin');
  el('task-btns').classList.toggle('hidden', !race);
  el('shared-btns').classList.toggle('hidden', app === null);
  if (race && trackData) buildTaskButtons(trackData, sendCmd);
  if (changed) {
    // reframe only when the app changes -- reconnects don't jump
    if (race) {
      frameField(camera, controls, trackData?.field);
    } else {
      camera.position.set(0.35, 0.25, -0.45);
      controls.target.set(0, 0.08, 0);
    }
  }
}

// ---------- WebSocket client ----------
let WS_URL = new URLSearchParams(location.search).get('ws') ?? 'ws://127.0.0.1:8765';
let ws: WebSocket | null = null;
let wsRetry: number | null = null;
let simWatchdog = 0;

function connectWS() {
  const sock = new WebSocket(WS_URL);
  ws = sock;   // newest socket wins; stale handlers no-op below
  sock.onopen = () => { if (ws === sock) setConn(true); };
  sock.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg?.type === 'scene') applyScene(msg);
      else applyState(msg);
    } catch (e) { console.error('bad frame:', e, ev.data); }
  };
  sock.onclose = () => {
    if (ws !== sock) return;
    setConn(false);
    if (wsRetry == null) wsRetry = window.setTimeout(() => { wsRetry = null; connectWS(); }, 1500);
  };
  sock.onerror = () => sock.close();
}
function sendCmd(obj: unknown) { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj)); }

// switch backends live (bot.ws("ws://127.0.0.1:8766")): drop the app
// identity so the UI goes neutral until the new server's scene frame
function switchWS(url: string) {
  WS_URL = url;
  if (wsRetry != null) { clearTimeout(wsRetry); wsRetry = null; }
  ws?.close();
  app = null;
  syncAppUI();
  connectWS();
}

// ---------- HUD wiring ----------
const hud = document.getElementById('hud')!;
const lineViewer = new LineViewer(el('line-panel'), robotRoot, scene, CAD_TO_THREE);
el('btn-guides').onclick = () => {
  routeGuides.visible = !routeGuides.visible;
  el('btn-guides').classList.toggle('active', routeGuides.visible);
};
el('btn-sensor-view').onclick = () => {
  sensorView = !sensorView;
  if (sensorView) {
    preSensorCamera = { position: camera.position.clone(), target: controls.target.clone() };
  }
  el('btn-sensor-view').classList.toggle('active', sensorView);
  el('btn-sensor-view').textContent = sensorView ? 'Show car' : 'Sensor view';
  el('btn-follow-car').classList.toggle('hidden', sensorView || app !== 'race');
  el('app').classList.toggle('sensor-focus', sensorView && app === 'race');
  setSensorFocus(sensorView && app === 'race');
  if (!sensorView) {
    if (preSensorCamera) {
      camera.position.copy(preSensorCamera.position);
      controls.target.copy(preSensorCamera.target);
      preSensorCamera = null;
    }
  } else if (lastState) applyState(lastState);
};
el('btn-follow-car').onclick = () => {
  raceFollow = !raceFollow;
  el('btn-follow-car').classList.toggle('active', raceFollow);
  resetFollow();
  if (raceFollow) {
    if (lastState) applyState(lastState);
  } else if (!sensorView) {
    frameField(camera, controls, trackData?.field);
  }
};

el('btn-kick-p').onclick = () => sendCmd({ type: 'nudge', tx: 3.5 });
el('btn-kick-n').onclick = () => sendCmd({ type: 'nudge', tx: -6.0 });
el('btn-reset').onclick = () => sendCmd({ type: 'reset' });
el('btn-pause').onclick = () => {
  const paused = lastState?.paused;
  sendCmd({ type: paused ? 'run' : 'pause' });
};
el('btn-mode').onclick = () => {
  const mode = lastState?.mode;
  const next = mode?.startsWith('drive') ? 'balance' : 'drive';
  sendCmd({ type: 'mode', mode: next, duty: 300 });
};

// ---------- Load glTF ----------
const loader = new GLTFLoader();
loader.load('/models/balance_bot.gltf', (gltf) => {
  const model = gltf.scene;
  (window as any).__bot = model;

  const root = model.children[0] ?? model;
  // re-parent the flat baked nodes under robotRoot (CAD frame verbatim;
  // add() keeps each node's local transform, and robotRoot supplies C)
  for (const node of [...root.children]) {
    robotRoot.add(node);
    cadNodes.push(node);
  }

  robotRoot.children.forEach((node) => {
    const info = PART_INFO[node.name];
    if (!info) return;
    const pos = node.position.clone();
    const explode = new THREE.Vector3(...info.explode);

    node.traverse((c) => {
      const m = (c as THREE.Mesh).material as THREE.MeshStandardMaterial;
      if (m) { m.metalness = 0; m.roughness = 0.8; }
      if ((c as THREE.Mesh).isMesh) {
        (c as THREE.Mesh).castShadow = true;
        (c as THREE.Mesh).receiveShadow = true;
      }
    });

    const entry: PartEntry = { node, name: info.label, base: pos, explode };
    parts.push(entry);
    nodeToEntry.set(node, entry);
  });
  for (const [key, label] of [['l', 'wheel_l_placeholder'], ['r', 'wheel_r_placeholder']] as const) {
    const node = robotRoot.children.find((c) => c.name === label) ?? null;
    wheelNodes[key] = node;
    wheelBakedQuat[key] = node ? node.quaternion.clone() : null;
    if (node) {
      // The purchased-wheel envelope is rotationally symmetric. A small
      // viewer-only spoke makes the streamed hinge angle inspectable.
      const spoke = new THREE.Mesh(new THREE.BoxGeometry(0.0015, 0.003, 0.025),
        new THREE.MeshBasicMaterial({ color: 0xffca62 }));
      spoke.name = 'wheel_spin_witness';
      spoke.position.set(0.031, 0, 0.024);
      node.add(spoke);
    }
  }

  hud.classList.remove('hidden');
  connectWS();

  // ---------- CLI ----------
  const byName = new Map<string, PartEntry[]>();
  for (const p of parts) {
    if (!byName.has(p.name)) byName.set(p.name, []);
    byName.get(p.name)!.push(p);
  }

  const bot = {
    list: () => [...byName.keys()],
    show: (n: string) => set(n, true),
    hide: (n: string) => set(n, false),
    only(n: string) {
      for (const [name, list] of byName) list.forEach(p => p.node.visible = name === n);
    },
    all() { for (const list of byName.values()) list.forEach(p => p.node.visible = true); },
    explode(t: number) {
      if (simLive && lastState && !lastState.paused) {
        console.warn('explode locked while the sim drives transforms; pause first');
        return;
      }
      for (const p of parts) p.node.position.copy(p.base).addScaledVector(p.explode, t);
    },
    grid(v: boolean) { grid.visible = v; },
    autoRotate(v: boolean) { controls.autoRotate = v; },
    cam(x: number, y: number, z: number, tx = 0, ty = 0.08, tz = 0) {
      camera.position.set(x, y, z);
      controls.target.set(tx, ty, tz);
    },
    // backend commands -- the same messages the HUD buttons send
    task(n: number) { sendCmd({ type: 'task', task: n }); },
    reset() { sendCmd({ type: 'reset' }); },
    pause() { sendCmd({ type: lastState?.paused ? 'run' : 'pause' }); },
    kick(sign: 1 | -1 = 1) { sendCmd({ type: 'nudge', tx: sign > 0 ? 3.5 : -6.0 }); },
    ws(url: string) { switchWS(url); },
  };
  function set(n: string, v: boolean) {
    const list = byName.get(n);
    if (!list) { console.warn(`no part "${n}"`); return; }
    list.forEach(p => p.node.visible = v);
  }
  (window as any).bot = bot;
  console.log('bot CLI ready:', bot.list().join(', '));
  console.log('cmds: bot.show/hide/only/all(name), bot.explode(0..1), bot.grid(bool), bot.autoRotate(bool), bot.cam(x,y,z,tx,ty,tz)');
  console.log('      bot.task(n), bot.reset(), bot.pause(), bot.kick(+1|-1), bot.ws("ws://127.0.0.1:8766")');

  document.getElementById('loading')!.classList.add('hidden');
}, undefined, (err: unknown) => {
  const el = document.getElementById('loading')!;
  el.textContent = 'ERR: ' + (err instanceof Error ? err.message : String(err));
  el.style.color = '#f66';
  console.error(err);
});

// ---------- Hover labels ----------
const tooltip = document.getElementById('tooltip')!;
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

canvas.addEventListener('pointermove', (e: PointerEvent) => {
  pointer.set((e.clientX / window.innerWidth) * 2 - 1,
              -(e.clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(parts.map(p => p.node), true);
  let entry: PartEntry | null = null;
  for (const hit of hits) {
    // walk up to the registered node; an invisible ancestor means the
    // part was hidden via the CLI and must not pick
    let o: THREE.Object3D | null = hit.object;
    let visible = true;
    let found: PartEntry | undefined;
    while (o) {
      if (o.visible === false) { visible = false; break; }
      found = nodeToEntry.get(o);
      if (found) break;
      o = o.parent;
    }
    if (visible && found) { entry = found; break; }
  }
  if (entry) {
    tooltip.textContent = entry.name;
    tooltip.style.left = `${e.clientX}px`;
    tooltip.style.top = `${e.clientY}px`;
    tooltip.classList.remove('hidden');
    canvas.style.cursor = 'pointer';
  } else {
    tooltip.classList.add('hidden');
    canvas.style.cursor = '';
  }
});
canvas.addEventListener('pointerleave', () => tooltip.classList.add('hidden'));

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  if (app === 'race' && !raceFollow && !sensorView) frameField(camera, controls, trackData?.field);
});

function animate() {
  requestAnimationFrame(animate);
  if (performance.now() - simWatchdog > 1000) simLive = false;
  applyInterpolatedPose(camera, controls, app === 'race' && raceFollow && !sensorView);
  updateHUD({ simLive, lastState, app, lineViewer });
  controls.update();
  renderer.render(scene, camera);
}
animate();
