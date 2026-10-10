// 01 · Cover
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // left accent block
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.16, h: 5.625, fill: { color: theme.accent }
  });

  slide.addText("DIGITAL TWIN", {
    x: 0.6, y: 0.55, w: 6, h: 0.3, margin: 0,
    fontSize: 13, color: theme.accent, bold: true,
    fontFace: "Arial", charSpacing: 3
  });

  slide.addText("两轮平衡赛车\n数字孪生系统", {
    x: 0.6, y: 1.05, w: 6.2, h: 1.5, margin: 0,
    fontSize: 40, color: theme.primary, bold: true,
    fontFace: "Microsoft YaHei", lineSpacing: 48, fit: "shrink"
  });

  slide.addText("MuJoCo 物理引擎 + 真实 STM32F407 固件在 Renode 中执行 + build123d CAD 单一几何源",
    {
      x: 0.6, y: 2.75, w: 6.2, h: 0.6, margin: 0,
      fontSize: 14, color: theme.secondary, fontFace: "Microsoft YaHei"
    });

  // right visual block
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 7.15, y: 0.9, w: 2.3, h: 3.85, fill: { color: theme.light }, rectRadius: 0.12
  });
  slide.addText("三控制器槽", {
    x: 7.3, y: 1.15, w: 2, h: 0.3, margin: 0,
    fontSize: 13, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  const slots = [
    ["stub", "Python 控制算法"],
    ["hostc", "宿主 C 库 (调参)"],
    ["renode", "真实固件 ELF"]
  ];
  slots.forEach((s, i) => {
    const y = 1.65 + i * 1.0;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 7.3, y: y, w: 2.0, h: 0.78, fill: { color: theme.bg },
      line: { color: theme.secondary, width: 0.75 }, rectRadius: 0.06
    });
    slide.addText(s[0], {
      x: 7.42, y: y + 0.06, w: 1.8, h: 0.28, margin: 0,
      fontSize: 14, color: theme.accent, bold: true, fontFace: "Consolas"
    });
    slide.addText(s[1], {
      x: 7.42, y: y + 0.36, w: 1.8, h: 0.32, margin: 0,
      fontSize: 10, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
  });

  slide.addShape(pres.shapes.LINE, {
    x: 0.6, y: 4.55, w: 5.6, h: 0, line: { color: theme.secondary, width: 0.75 }
  });
  slide.addText("github.com/rim5432/mujoco-renode-twin   |   MIT License", {
    x: 0.6, y: 4.68, w: 6, h: 0.3, margin: 0,
    fontSize: 11, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };