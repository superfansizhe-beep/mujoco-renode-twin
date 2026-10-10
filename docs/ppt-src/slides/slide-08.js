// 08 · 3D viewer demo (image showcase) - real screenshot
const nodePath = require('path');
const ASSETS = nodePath.join(__dirname, '..', 'assets');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("3D 浏览器查看器", {
    x: 0.5, y: 0.40, w: 6, h: 0.5, margin: 0,
    fontSize: 28, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("three.js 实时渲染, 30Hz 状态帧, 一条命令拉起", {
    x: 0.5, y: 0.90, w: 6, h: 0.3, margin: 0,
    fontSize: 12, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // hero screenshot (1280x720)
  slide.addImage({
    path: nodePath.join(ASSETS, "task1.png"),
    x: 0.5, y: 1.25, w: 5.95, h: 3.35,
    altText: "3D twin viewer: task 1 graded"
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.25, w: 5.95, h: 3.35,
    fill: { color: "FFFFFF", transparency: 100 },
    line: { color: theme.secondary, width: 0.75 }
  });

  // sensor close-up (436x871) - right column
  slide.addImage({
    path: nodePath.join(ASSETS, "task2.png"),
    x: 6.6, y: 1.25, w: 1.5, h: 3.0,
    altText: "8-channel line sensor array close-up"
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.6, y: 1.25, w: 1.5, h: 3.0,
    fill: { color: "FFFFFF", transparency: 100 },
    line: { color: theme.secondary, width: 0.75 }
  });

  // right notes
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 8.25, y: 1.25, w: 1.25, h: 3.0, fill: { color: theme.light }, rectRadius: 0.08
  });
  slide.addText("画面可读信息", {
    x: 8.35, y: 1.4, w: 1.05, h: 0.28, margin: 0,
    fontSize: 10, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });
  const notes = [
    "实时姿态",
    "Tilt / Pos",
    "Duty 占空比",
    "Enc 编码器",
    "电池电压",
    "8 通道循迹读数",
    "停车判定"
  ];
  notes.forEach((n, i) => {
    slide.addText("- " + n, {
      x: 8.35, y: 1.78 + i * 0.33, w: 1.1, h: 0.3, margin: 0,
      fontSize: 8.5, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.72, w: 8.6, h: 0.55, fill: { color: theme.primary }, rectRadius: 0.07
  });
  slide.addText("bash tools/demo.sh   ->   http://localhost:5173/?ws=ws://127.0.0.1:8766   (四任务一键切换, 四档回放倍速)", {
    x: 0.72, y: 4.72, w: 8.2, h: 0.55, margin: 0, valign: "middle",
    fontSize: 11, color: "FFFFFF", fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("10", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };