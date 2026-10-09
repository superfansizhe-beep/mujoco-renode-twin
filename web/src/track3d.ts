// ---------- Race mode: 3D track ----------
// The track mesh from the scene frame's payload (race/scene.py): field
// plate, the two taped arcs as annular sectors matching the analytic
// sensor mask, and the untaped legs as ghost strips (the field marks
// only the arcs -- every straight is open white the car dead-reckons
// across). Built once, toggled by the app mode.
import * as THREE from 'three';
import { CAD_TO_THREE } from './frame';
import type { TrackData } from './protocol';

export function buildTrack(t: TrackData, routeGuides: THREE.Group): THREE.Object3D {
  const root = new THREE.Object3D();
  root.matrixAutoUpdate = false;
  root.matrix.copy(CAD_TO_THREE);          // same CAD->three frame as robotRoot

  const [fx, fy] = t.field;
  const plate = new THREE.Mesh(
    new THREE.BoxGeometry(fx, fy, 0.004),
    new THREE.MeshStandardMaterial({ color: 0xe9e4d8, roughness: 0.95, metalness: 0 }));
  plate.position.set(fx / 2, fy / 2, -0.002);          // top face at z = 0
  plate.receiveShadow = true;
  root.add(plate);

  // Annular sectors match the analytic sensor mask, including square ends.
  const tapeMat = new THREE.MeshStandardMaterial({ color: 0x14161a, roughness: 0.9,
    metalness: 0, side: THREE.DoubleSide });
  const w = t.tape_half * 2;
  for (const tp of t.tapes) {
    if (!tp.center) continue;       // stale server: do not invent tape geometry
    const arc = new THREE.Mesh(new THREE.RingGeometry(tp.radius - w / 2,
      tp.radius + w / 2, Math.ceil(Math.abs(tp.sweep) * tp.radius / 0.004),
      1, tp.start, tp.sweep), tapeMat);
    arc.position.set(tp.center[0], tp.center[1], 0.0008);
    root.add(arc);
  }
  // the untaped legs as thin ghost strips
  root.add(routeGuides);
  const ghostMat = new THREE.LineDashedMaterial({ color: 0x5c9bb3,
    dashSize: 0.012, gapSize: 0.012, transparent: true, opacity: 0.45 });
  for (const gp of t.ghosts) {
    const [x0, y0] = gp.poly[0];
    const [x1, y1] = gp.poly[gp.poly.length - 1];
    const seg = new THREE.Line(new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x0, y0, 0.001), new THREE.Vector3(x1, y1, 0.001)]), ghostMat);
    seg.computeLineDistances(); routeGuides.add(seg);
  }
  return root;
}

// Fit the whole field in view (used on scene switch and resize).
export function frameField(camera: THREE.PerspectiveCamera,
                           controls: { target: THREE.Vector3 },
                           field: [number, number] | undefined) {
  const [width, depth] = field ?? [2.2, 1.2];
  const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
  const distance = 1.3 * Math.max(width / (2 * Math.tan(halfFov) * camera.aspect),
    depth / (2 * Math.tan(halfFov)));
  const target = new THREE.Vector3(width / 2, 0, -depth / 2);
  camera.position.copy(target).add(new THREE.Vector3(0, distance * 0.78, -distance * 0.62));
  controls.target.copy(target);
}
