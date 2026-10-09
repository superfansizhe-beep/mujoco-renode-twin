// ---------- Pose plumbing ----------
// States arrive at the wire rate (~30 Hz) but rendering runs at rAF: the
// pose buffer bridges the two, so displayed motion interpolates between
// authoritative snapshots (rendered INTERP_DELAY_MS behind). HUD numbers,
// line lamps and the sensor overlay always read the newest state frame --
// only placement is interpolated, never a measured value.
//
// Placement only: blend buffered poses for the render instant and drive
// the follow camera from the same blended ground track (a stepped camera
// over an interpolated body reads as wobble). Holds the newest pose when
// the buffer starves; never extrapolates.
import * as THREE from 'three';
import { CAD_TO_THREE, robotRoot } from './frame';

export interface PoseSample { recv: number; pos: THREE.Vector3; quat: THREE.Quaternion; wheelDeg: [number, number]; }
export const poseBuf: PoseSample[] = [];
export const INTERP_DELAY_MS = 50;   // ~1.5 wire frames; covers p95 delivery gaps
const FOLLOW_OFFSET = new THREE.Vector3(0.35, 0.35, 0.42);
let followPrev: THREE.Vector3 | null = null;   // interpolated ground track

export const wheelNodes: Record<string, THREE.Object3D | null> = { l: null, r: null };
export const wheelBakedQuat: Record<string, THREE.Quaternion | null> = { l: null, r: null };
const WHEEL_HINGE_AXIS = new THREE.Vector3(-1, 0, 0); // MuJoCo joint axis in the chassis frame

export function pushPose(st: { pos: number[]; quat_xyzw: number[]; wheel_deg: number[] }) {
  poseBuf.push({ recv: performance.now(),
    pos: new THREE.Vector3(st.pos[0], st.pos[1], st.pos[2]),
    quat: new THREE.Quaternion(st.quat_xyzw[0], st.quat_xyzw[1],
                               st.quat_xyzw[2], st.quat_xyzw[3]),
    wheelDeg: [st.wheel_deg[0], st.wheel_deg[1]] });
  if (poseBuf.length > 8) poseBuf.shift();
}

export function resetFollow() { followPrev = null; }

const _ipos = new THREE.Vector3();
const _iquat = new THREE.Quaternion();
export function applyInterpolatedPose(camera: THREE.Camera,
                                      controls: { target: THREE.Vector3 },
                                      follow: boolean) {
  const n = poseBuf.length;
  if (n === 0) return;
  const renderT = performance.now() - INTERP_DELAY_MS;
  let a = poseBuf[n - 1], b = a, alpha = 0;
  for (let i = n - 2; i >= 0; i--) {
    if (poseBuf[i].recv <= renderT) { a = poseBuf[i]; b = poseBuf[i + 1]; break; }
  }
  if (b.recv > a.recv && renderT < b.recv) alpha = (renderT - a.recv) / (b.recv - a.recv);
  _ipos.lerpVectors(a.pos, b.pos, alpha);
  _iquat.copy(a.quat).slerp(b.quat, alpha);
  robotRoot.matrix.multiplyMatrices(CAD_TO_THREE, new THREE.Matrix4().compose(
    _ipos, _iquat, new THREE.Vector3(1, 1, 1)));

  // Both MuJoCo wheel hinges turn about chassis -X. The left GLTF node has
  // a baked Z half-turn, so spin must precede that baked orientation.
  for (const side of ['l', 'r'] as const) {
    const node = wheelNodes[side];
    const baked = wheelBakedQuat[side];
    if (!node || !baked) continue;
    const idx = side === 'l' ? 0 : 1;
    const deg = a.wheelDeg[idx] + (b.wheelDeg[idx] - a.wheelDeg[idx]) * alpha;
    node.quaternion.copy(baked).premultiply(
      new THREE.Quaternion().setFromAxisAngle(WHEEL_HINGE_AXIS, THREE.MathUtils.degToRad(deg)));
  }

  if (follow) {
    const target = new THREE.Vector3(_ipos.x, 0.035, -_ipos.y);
    if (followPrev) {
      camera.position.add(target.clone().sub(followPrev));
    } else {
      camera.position.copy(target).add(FOLLOW_OFFSET);
    }
    controls.target.copy(target);
    followPrev = target;
  } else {
    followPrev = null;
  }
}
