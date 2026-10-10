// 06b · CAD modelling with build123d + GrabCAD (data source) - mixed media
const nodePath = require('path');
const ASSETS = nodePath.join(__dirname, '..', 'assets');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("机械建模: build123d 单一几何源", {
    x: 0.5, y: 0.35, w: 6.5, h: 0.5, margin: 0,
    fontSize: 28, color: theme.primary, bold: true, fontFace: "Microsoft YaHei", fit: "shrink"
  });
  slide.addText("车不是画出来的, 是算出来的 -- 同一份尺寸数据同时喂给物理引擎和 3D 查看器", {
    x: 0.5, y: 0.85, w: 9, h: 0.3, margin: 0,
    fontSize: 12, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // ---------- left: one source, two outputs ----------
  slide.addText("一份数据, 两个出口", {
    x: 0.5, y: 1.28, w: 4.5, h: 0.28, margin: 0,
    fontSize: 14, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  // source box
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.66, w: 4.4, h: 0.62, fill: { color: theme.accent }, rectRadius: 0.08
  });
  slide.addText("constants sheet  (layout.py / 各零件模块)", {
    x: 0.5, y: 1.66, w: 4.4, h: 0.62, margin: 0, align: "center", valign: "middle",
    fontSize: 12, color: "FFFFFF", bold: true, fontFace: "Consolas"
  });

  // arrows
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 1.25, y: 2.3, w: 0.05, h: 0.28, fill: { color: theme.secondary }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 4.05, y: 2.3, w: 0.05, h: 0.28, fill: { color: theme.secondary }
  });

  // two outputs
  const outs = [
    ["物理碰撞体", "collision 模式", "包络体 (Box/Cylinder)\n喂给 MuJoCo 算碰撞", theme.primary],
    ["3D 显示模型", "visual 模式", "换成厂商真实 STEP\nexport STEP / GLB", theme.secondary]
  ];
  outs.forEach((o, i) => {
    const x = 0.5 + i * 2.35;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: 2.6, w: 2.05, h: 1.15, fill: { color: theme.light }, rectRadius: 0.08
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: 2.6, w: 2.05, h: 0.06, fill: { color: o[3] }
    });
    slide.addText(o[0], {
      x: x + 0.12, y: 2.74, w: 1.8, h: 0.28, margin: 0,
      fontSize: 12, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(o[1], {
      x: x + 0.12, y: 3.0, w: 1.8, h: 0.24, margin: 0,
      fontSize: 9, color: theme.accent, bold: true, fontFace: "Consolas"
    });
    slide.addText(o[2], {
      x: x + 0.12, y: 3.24, w: 1.8, h: 0.48, margin: 0,
      fontSize: 8.5, color: theme.secondary, fontFace: "Microsoft YaHei", lineSpacing: 11
    });
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 3.92, w: 4.4, h: 0.92, fill: { color: theme.primary }, rectRadius: 0.08
  });
  slide.addText("同一套尺寸, 物理与显示不可能对不上", {
    x: 0.65, y: 4.02, w: 4.1, h: 0.28, margin: 0,
    fontSize: 12, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("装错位, 算错质量, 重心偏移都会立刻暴露 -- 而这些数直接决定车能不能站稳", {
    x: 0.65, y: 4.32, w: 4.1, h: 0.45, margin: 0,
    fontSize: 10, color: "FFFFFF", fontFace: "Microsoft YaHei"
  });

  // ---------- right: GrabCAD / vendor sourcing ----------
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.15, y: 1.28, w: 4.35, h: 3.56, fill: { color: theme.light }, rectRadius: 0.1
  });
  slide.addText("买来的零件模型从哪来", {
    x: 5.35, y: 1.42, w: 4.0, h: 0.28, margin: 0,
    fontSize: 14, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  const src = [
    ["GitHub 开源仓库", "JGB37-520 电机 7 件 / GY-521 / AMS1117"],
    ["GrabCAD", "需登录下载, 引擎 LR24 + 尺寸图"]
  ];
  src.forEach((s, i) => {
    const y = 1.82 + i * 0.72;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 5.35, y: y, w: 3.95, h: 0.62, fill: { color: theme.bg }, rectRadius: 0.06
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 5.35, y: y, w: 0.06, h: 0.62, fill: { color: theme.accent }
    });
    slide.addText(s[0], {
      x: 5.5, y: y + 0.06, w: 3.7, h: 0.24, margin: 0,
      fontSize: 11, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(s[1], {
      x: 5.5, y: y + 0.3, w: 3.7, h: 0.26, margin: 0,
      fontSize: 9, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
  });

  slide.addText("三源交叉验证, 法兰尺寸由此定案", {
    x: 5.35, y: 3.3, w: 3.95, h: 0.26, margin: 0,
    fontSize: 11, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });
  const tri = ["尺寸图", "GrabCAD", "GitHub"];
  tri.forEach((t, i) => {
    const x = 5.35 + i * 1.33;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: 3.6, w: 1.2, h: 0.4, fill: { color: theme.primary }, rectRadius: 0.06
    });
    slide.addText(t, {
      x: x, y: 3.6, w: 1.2, h: 0.4, margin: 0, align: "center", valign: "middle",
      fontSize: 10, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
    });
  });
  slide.addText("三者一致 -> 6 个 M3 孔, 节圆 31mm, 攻丝深 3.5mm", {
    x: 5.35, y: 4.08, w: 3.95, h: 0.26, margin: 0,
    fontSize: 9.5, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });

  // license honesty
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.35, y: 4.38, w: 3.95, h: 0.38, fill: { color: theme.bg },
    line: { color: theme.accent, width: 0.75 }, rectRadius: 0.06
  });
  slide.addText("第三方模型只取用不分发, 碰撞体一律自己算", {
    x: 5.45, y: 4.38, w: 3.75, h: 0.38, margin: 0, valign: "middle",
    fontSize: 9, color: theme.primary, fontFace: "Microsoft YaHei"
  });

  // footer
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.95, w: 8.6, h: 0.42, fill: { color: theme.accent }, rectRadius: 0.06
  });
  slide.addText("src/cad_modeling/  11 个模块 1246 行 Python -- 用代码写零件, 不是用鼠标点", {
    x: 0.68, y: 4.95, w: 8.3, h: 0.42, margin: 0, valign: "middle",
    fontSize: 10.5, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("07", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };