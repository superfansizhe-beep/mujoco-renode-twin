// 08 · The exam task this twin is graded against (image showcase) - mixed media
const nodePath = require('path');
const ASSETS = nodePath.join(__dirname, '..', 'assets');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("赛题要求: 小车行驶场地与四项任务", {
    x: 0.5, y: 0.35, w: 9, h: 0.5, margin: 0,
    fontSize: 28, color: theme.primary, bold: true, fontFace: "Microsoft YaHei", fit: "shrink"
  });
  slide.addText("孪生不是自娱自乐的靶场 -- 它逐条复现考题, 并按同一套判分标准打分", {
    x: 0.5, y: 0.87, w: 9, h: 0.3, margin: 0,
    fontSize: 12, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // official problem sheet (979x893)
  slide.addImage({
    path: nodePath.join(ASSETS, "problem.jpg"),
    x: 0.5, y: 1.28, w: 3.62, h: 3.3,
    altText: "2024 H sheet smart-car exam: field layout and four tasks"
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.28, w: 3.62, h: 3.3,
    fill: { color: "FFFFFF", transparency: 100 },
    line: { color: theme.secondary, width: 0.75 }
  });
  slide.addText("赛题原图", {
    x: 0.5, y: 4.62, w: 3.62, h: 0.24, margin: 0, align: "center",
    fontSize: 9, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // four requirements
  slide.addText("四项任务 (与仿真一一对应)", {
    x: 4.4, y: 1.28, w: 5.1, h: 0.28, margin: 0,
    fontSize: 14, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  const tasks = [
    ["任务 1", "A -> B 直线行驶并停车, 声光提示", "限 15 秒"],
    ["任务 2", "A -> B -> C -> D -> A, 每经一点提示一次", "限 30 秒"],
    ["任务 3", "A -> C -> B -> D -> A, 每经一点提示一次", "限 40 秒"],
    ["任务 4", "按任务 3 路线连跑 4 圈, 用时越少越好", "不限时"]
  ];
  tasks.forEach((t, i) => {
    const y = 1.66 + i * 0.78;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 4.4, y: y, w: 5.1, h: 0.68, fill: { color: theme.light }, rectRadius: 0.07
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 4.4, y: y, w: 0.07, h: 0.68, fill: { color: theme.accent }
    });
    slide.addText(t[0], {
      x: 4.58, y: y + 0.08, w: 0.95, h: 0.26, margin: 0,
      fontSize: 12, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(t[1], {
      x: 5.55, y: y + 0.08, w: 3.85, h: 0.26, margin: 0,
      fontSize: 11, color: theme.primary, fontFace: "Microsoft YaHei"
    });
    slide.addText(t[2], {
      x: 5.55, y: y + 0.36, w: 3.85, h: 0.24, margin: 0,
      fontSize: 10, color: theme.secondary, bold: true, fontFace: "Microsoft YaHei"
    });
  });

  // geometry note
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 4.4, y: 4.78, w: 4.7, h: 0.6, fill: { color: theme.primary }, rectRadius: 0.07
  });
  slide.addText("场地 220 x 120 cm, 半径 40 cm 半弧; 尺寸直接来自题图", {
    x: 4.58, y: 4.78, w: 4.45, h: 0.6, margin: 0, valign: "middle",
    fontSize: 10, color: "FFFFFF", fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("08", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };