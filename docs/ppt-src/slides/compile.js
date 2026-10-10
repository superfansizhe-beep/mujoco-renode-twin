const pptxgen = require('pptxgenjs');
const path = require('path');
const fs = require('fs');

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = 'rim5432';
pres.title = 'Two-wheel balancing race car digital twin';

// Tech & Night-inspired, mapped for a light deck.
// primary = body text, secondary = muted, accent = highlight, light = card, bg = page
const theme = {
  primary: '023047',
  secondary: '5c6b7a',
  accent: 'fb8500',
  light: 'e8f1f5',
  bg: 'f7fafc'
};

const order = [
  './slide-01.js', './slide-02.js', './slide-03.js', './slide-04.js', './slide-05.js',
  './slide-06.js', './slide-06b.js', './slide-07b.js', './slide-07.js', './slide-08.js', './slide-09.js',
  './slide-10.js'
];

order.forEach(f => require(path.join(__dirname, f)).createSlide(pres, theme));

const outDir = path.join(__dirname, 'output');
fs.mkdirSync(outDir, { recursive: true });
const out = path.join(outDir, 'mujoco-renode-twin-defense.pptx');
pres.writeFile({ fileName: out })
  .then(() => console.log('written:', out))
  .catch(e => { console.error("FAILED:", e.message); console.error(e.stack.split("\n").slice(0,8).join("\n")); process.exit(1); });