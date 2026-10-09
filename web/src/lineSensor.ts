import * as THREE from 'three';

export interface LineConfig {
  count: number; pitch_m: number; positions: number[][];
  indicator_z_m: number; indicator_y_m: number;
  footprint_radius_m: number; calibration: string;
}
export interface LineState {
  black_bits: number; indicator_bits: number; gpio_bits: number;
  valid_bits: number; coverage: number[]; illumination_on: boolean;
  spots: (number[] | null)[]; positions: number[][];
  seq: number | null; consumed_bits: number | null; matches: boolean;
  expected_tape: boolean;
  observation: { status: string; valid: boolean; count: number;
    error_mm: number | null; bar_centered: boolean };
}

export class LineViewer {
  private config: LineConfig | null = null;
  private local = new THREE.Group();
  private world = new THREE.Group();
  private lamps: THREE.Mesh[] = [];
  private spots: THREE.Mesh[] = [];
  private beams = new THREE.LineSegments(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0x62cad5, transparent: true, opacity: 0.30,
      depthTest: false, depthWrite: false }));
  private cells: HTMLElement[] = [];
  private enabled = false;

  constructor(private panel: HTMLElement, robot: THREE.Object3D,
              scene: THREE.Scene, cadToThree: THREE.Matrix4) {
    robot.add(this.local);
    this.world.matrixAutoUpdate = false;
    this.world.matrix.copy(cadToThree);
    this.beams.renderOrder = 1;
    this.world.add(this.beams);
    scene.add(this.world);
    panel.innerHTML = `<div class="line-heading"><strong>8-channel line array</strong>
      <span class="line-illumination">Continuous illumination</span></div>
      <div class="line-legend">LED on = white floor · LED off = black tape</div>
      <div class="line-sides"><span>Travel left (+)</span><span>Travel right (−)</span></div>
      <div class="line-channels"></div>
      <div class="line-center-note">Array center lies between channels 4 and 3</div>
      <div class="line-status" role="status">Waiting for sensor data</div>
      <div class="line-correction"></div><div class="line-bits"></div>
      <details><summary>Sensor model</summary><div class="line-calibration"></div></details>`;
  }

  configure(config: LineConfig) {
    if (config.count !== 8 || config.positions.length !== 8) return;
    this.disposeChildren(this.local);
    for (const spot of this.spots) { this.world.remove(spot); this.disposeMesh(spot); }
    this.lamps = []; this.spots = []; this.cells = [];
    this.config = config;
    this.panel.querySelector('.line-calibration')!.textContent =
      `${(config.pitch_m * 1000).toFixed(1)} mm channel pitch; ` +
      `${(config.footprint_radius_m * 2000).toFixed(1)} mm assumed spot diameter. ` + config.calibration;
    const row = this.panel.querySelector('.line-channels')!;
    row.textContent = '';
    // CAD +X is travel-left: channel 7 is on the left in this panel.
    for (let i = 7; i >= 0; --i) {
      const cell = document.createElement('div');
      cell.className = 'line-channel';
      cell.innerHTML = `<span class="channel-lamp"></span><span class="channel-number">${i}</span>
        <span class="channel-ground">—</span><span class="channel-coverage"><i></i></span>`;
      row.appendChild(cell); this.cells[i] = cell;
    }
    for (let i = 0; i < 8; ++i) {
      const p = config.positions[i];
      const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.0022, 12, 8),
        new THREE.MeshStandardMaterial({ color: 0x37434a, roughness: 0.4, transparent: true,
          depthTest: false, depthWrite: false }));
      lamp.renderOrder = 2;     // diagnostic indicators remain readable through the chassis
      lamp.position.set(p[0], config.indicator_y_m, config.indicator_z_m);
      this.local.add(lamp); this.lamps.push(lamp);
      const label = this.channelLabel(i);
      if (label) {
        label.position.set(p[0], config.indicator_y_m + 0.006, config.indicator_z_m + 0.006);
        this.local.add(label);
      }
      // Optical apertures stay fixed; detection never switches illumination off.
      const aperture = new THREE.Mesh(new THREE.CircleGeometry(0.0024, 12),
        new THREE.MeshBasicMaterial({ color: 0x152e35, side: THREE.DoubleSide }));
      aperture.position.set(p[0], p[1], p[2]); this.local.add(aperture);
      const spot = new THREE.Mesh(new THREE.CircleGeometry(config.footprint_radius_m, 16),
        new THREE.MeshBasicMaterial({ color: 0x62cad5, transparent: true, opacity: 0.85,
          side: THREE.DoubleSide, depthTest: false, depthWrite: false }));
      spot.renderOrder = 1;
      this.world.add(spot); this.spots.push(spot);
    }
    this.beams.geometry.dispose();
    this.beams.geometry = new THREE.BufferGeometry();
    this.beams.geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(48), 3));
    this.show(this.enabled);
  }

  show(enabled: boolean) {
    this.enabled = enabled;
    this.panel.classList.toggle('hidden', !enabled);
    this.local.visible = enabled && this.config !== null;
    this.world.visible = enabled && this.config !== null;
  }

  update(line: LineState | undefined, correction: number | undefined, source: string | undefined) {
    if (!this.enabled) return;
    const status = this.panel.querySelector('.line-status') as HTMLElement;
    if (!this.config || !line || !Array.isArray(line.coverage) || line.coverage.length !== 8
        || !Array.isArray(line.positions) || line.positions.length !== 8
        || !Array.isArray(line.spots) || line.spots.length !== 8 || !line.observation) {
      status.textContent = 'Waiting for live sensor data';
      status.classList.add('ambiguous');
      this.world.visible = this.local.visible = false;
      this.cells.forEach((c, i) => {
        c.className = 'line-channel unknown';
        c.setAttribute('aria-label', `Channel ${i}: waiting for live data`);
        c.querySelector('.channel-ground')!.textContent = '—';
        (c.querySelector('.channel-coverage i') as HTMLElement).style.width = '0';
      });
      this.panel.querySelector('.line-correction')!.textContent = '';
      this.panel.querySelector('.line-bits')!.textContent = '';
      return;
    }
    this.world.visible = this.local.visible = true;
    const coords = this.beams.geometry.getAttribute('position') as THREE.BufferAttribute;
    let n = 0;
    for (let i = 0; i < 8; ++i) {
      const black = !!(line.black_bits & (1 << i));
      const on = !!(line.indicator_bits & (1 << i));
      const valid = !!(line.valid_bits & (1 << i));
      const cell = this.cells[i];
      cell.className = 'line-channel ' + (on ? 'led-on' : 'led-off') + (valid ? '' : ' out-of-range');
      cell.setAttribute('aria-label', `Channel ${i}: ${valid ? black ? 'black tape' : 'white floor' : 'out of range'}; LED ${on ? 'on' : 'off'}`);
      cell.querySelector('.channel-ground')!.textContent = valid ? (black ? 'Black' : 'White') : 'Range';
      (cell.querySelector('.channel-coverage i') as HTMLElement).style.width = `${line.coverage[i] * 100}%`;
      const material = this.lamps[i].material as THREE.MeshStandardMaterial;
      material.color.setHex(on ? 0xffed86 : 0x20282c);
      material.emissive.setHex(on ? 0xffc832 : 0x000000);
      material.emissiveIntensity = on ? 1.4 : 0;
      const p = line.spots[i];
      this.spots[i].visible = p !== null;
      if (p) {
        this.spots[i].position.set(p[0], p[1], p[2]);
        coords.setXYZ(n++, ...line.positions[i] as [number, number, number]);
        coords.setXYZ(n++, ...p as [number, number, number]);
      }
    }
    coords.needsUpdate = true;
    this.beams.geometry.setDrawRange(0, n);
    this.beams.geometry.computeBoundingSphere();
    const obs = line.observation;
    let text: string;
    if (!line.matches) text = 'Sensor / controller mismatch';
    else if (line.valid_bits !== 255) text = 'Detection range exceeded · centering unavailable';
    else if (obs.status === 'split') text = 'Split detection · centering ambiguous';
    else if (obs.status === 'wide') text = 'Wide detection · centering ambiguous';
    else if (!obs.valid) text = line.expected_tape ? 'Line lost · recovering' : 'Open floor · planned odometry';
    else if (obs.bar_centered) text = 'Line under array center · heading is separate';
    else text = `Line ${obs.error_mm! > 0 ? 'left' : 'right'} of array · ${Math.abs(obs.error_mm!).toFixed(1)} mm`;
    status.textContent = text;
    status.classList.toggle('ambiguous', !line.matches || !obs.valid || line.valid_bits !== 255);
    this.panel.querySelector('.line-correction')!.textContent = correction === undefined ? '' :
      `Steering error ${correction >= 0 ? '+' : ''}${correction.toFixed(1)} mm · ` +
      ({ sensor: 'fresh sensor', hold: 'brief hold', odometry: 'odometry estimate' }[source ?? ''] ?? 'awaiting cycle');
    this.panel.querySelector('.line-bits')!.textContent =
      `Black ${line.black_bits.toString(2).padStart(8, '0')} · GPIO ${line.gpio_bits.toString(2).padStart(8, '0')}`;
  }

  private disposeMesh(mesh: THREE.Mesh) {
    mesh.geometry.dispose();
    (mesh.material as THREE.Material).dispose();
  }
  private disposeChildren(group: THREE.Group) {
    for (const child of [...group.children]) {
      group.remove(child);
      if (child instanceof THREE.Sprite) {
        child.material.map?.dispose();
        child.material.dispose();
      } else if (child instanceof THREE.Mesh) this.disposeMesh(child);
    }
  }

  private channelLabel(index: number): THREE.Sprite | undefined {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 64;
    const context = canvas.getContext('2d');
    if (!context) return;
    context.fillStyle = 'rgba(20, 28, 34, 0.9)';
    context.beginPath(); context.arc(32, 32, 28, 0, Math.PI * 2); context.fill();
    context.fillStyle = '#e6edf2';
    context.font = '600 40px system-ui';
    context.textAlign = 'center'; context.textBaseline = 'middle';
    context.fillText(String(index), 32, 33);
    const label = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas), transparent: true, depthTest: false }));
    label.scale.set(0.007, 0.007, 1);
    label.renderOrder = 3;
    return label;
  }
}
