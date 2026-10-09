// ---------- CAD frame ----------
// The glTF is RAW CAD coordinates (OCCT export, z-up, meters) inside a
// three.js scene (y-up). The CAD->three rotation C = Rx(-90 deg) maps
// (x, y, z)_cad -> (x, z, -y): the bot stands upright on the grid and
// the floor plane (z_cad = 0) coincides with the GridHelper plane.
import * as THREE from 'three';

export const CAD_TO_THREE = new THREE.Matrix4().makeRotationX(-Math.PI / 2);

// robotRoot: world = C * (CAD chassis pose). matrixAutoUpdate stays off;
// the pose arrives as [x, y, z] + quat (w x y z), both CAD-frame SI.
export const robotRoot = new THREE.Object3D();
robotRoot.matrixAutoUpdate = false;
robotRoot.matrix.multiplyMatrices(CAD_TO_THREE, new THREE.Matrix4());
