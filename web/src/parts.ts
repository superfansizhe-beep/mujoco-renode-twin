// ---------- Part registry ----------
import * as THREE from 'three';

export interface PartEntry {
  node: THREE.Object3D;
  name: string;
  base: THREE.Vector3;
  explode: THREE.Vector3;
}
export const parts: PartEntry[] = [];
export const nodeToEntry = new Map<THREE.Object3D, PartEntry>();
export const cadNodes: THREE.Object3D[] = [];
const sensorFocusVisibility = new Map<THREE.Object3D, boolean>();

export function setSensorFocus(enabled: boolean) {
  if (enabled) {
    for (const node of cadNodes) {
      if (!sensorFocusVisibility.has(node)) sensorFocusVisibility.set(node, node.visible);
      node.visible = false;
    }
  } else {
    for (const [node, visible] of sensorFocusVisibility) node.visible = visible;
    sensorFocusVisibility.clear();
  }
}

export const PART_INFO: Record<string, { label: string; explode: [number, number, number] }> = {
  wheel_r_placeholder: { label: 'Right wheel (bought, placeholder)', explode: [ 0.06, 0, 0] },
  wheel_l_placeholder: { label: 'Left wheel (bought, placeholder)',  explode: [-0.06, 0, 0] },
  motor_r_visual:      { label: 'Right motor (vendor STEP)',         explode: [ 0.035, 0, 0] },
  motor_l_visual:      { label: 'Left motor (vendor STEP)',          explode: [-0.035, 0, 0] },
  motor_r_envelope:    { label: 'Right motor (envelope)',            explode: [ 0.035, 0, 0] },
  motor_l_envelope:    { label: 'Left motor (envelope)',            explode: [-0.035, 0, 0] },
  bracket_r_visual:    { label: 'Right L-bracket (bought)',          explode: [-0.03, 0, -0.03] },
  bracket_l_visual:    { label: 'Left L-bracket (bought)',           explode: [ 0.03, 0, -0.03] },
  bracket_r_envelope:  { label: 'Right L-bracket (bought)',          explode: [-0.03, 0, -0.03] },
  bracket_l_envelope:  { label: 'Left L-bracket (bought)',           explode: [ 0.03, 0, -0.03] },
  deck_lower:          { label: 'Deck disc, lower (laser, x2)',      explode: [0, 0, 0.03] },
  deck_upper:          { label: 'Deck disc, upper (laser, x2)',      explode: [0, 0, 0.07] },
  standoffs:           { label: 'Tier standoffs (bought, x4)',       explode: [0, 0, 0.05] },
  sonar_bracket:       { label: 'Sonar bracket (bought, guess dims)', explode: [0, 0.05, 0.05] },
  sonar:               { label: 'HC-SR04 sonar (bought)',            explode: [0, 0.08, 0.05] },
  line_posts:          { label: 'Line-bar posts (bought, x2)',       explode: [0, -0.03, -0.03] },
  line_sensor:         { label: '8-way line bar (bought, guess dims)', explode: [0, -0.06, -0.06] },
  battery:             { label: 'Battery (provisional 34×106×22 mm)',        explode: [0, -0.04, 0] },
  motor_driver:        { label: 'Motor driver (placeholder 21x16x3, GUESS)', explode: [0.05, 0, 0] },
  mcu:                 { label: 'MCU (placeholder 36x27x3, GUESS)',          explode: [0, 0.04, 0.07] },
  imu:                 { label: 'IMU — GY-521 / MPU6050 (vendor board)',     explode: [-0.05, 0, 0] },
};
