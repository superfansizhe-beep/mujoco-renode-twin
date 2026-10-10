// 02 · The problem (why simulation)
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("为什么要做数字孪生", {
    x: 0.5, y: 0.4, w: 9, h: 0.55, margin: 0,
    fontSize: 30, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  // Left: the slow loop
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.15, w: 4.35, h: 3.5, fill: { color: theme.light }, rectRadius: 0.1
  });
  slide.addText("实物调参循环", {
    x: 0.75, y: 1.35, w: 3.8, h: 0.3, margin: 0,
    fontSize: 16, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  const steps = ["改代码", "交叉编译", "烧录板子", "放上赛道", "跑", "失败", "重改"];
  steps.forEach((s, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.75 + col * 1.95, y = 1.85 + row * 0.62;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: y, w: 1.75, h: 0.46, fill: { color: theme.bg },
      line: { color: theme.secondary, width: 0.75 }, rectRadius: 0.05
    });
    slide.addText(s, {
      x: x, y: y, w: 1.75, h: 0.46, margin: 0, align: "center", valign: "middle",
      fontSize: 12, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
  });

  slide.addText("一轮数分钟, 失败后无法定位是哪一环出错", {
    x: 0.75, y: 4.28, w: 3.9, h: 0.32, margin: 0,
    fontSize: 10.5, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });

  // Right: the fast loop
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.15, y: 1.15, w: 4.35, h: 3.5, fill: { color: theme.primary }, rectRadius: 0.1
  });
  slide.addText("数字孪生调参循环", {
    x: 5.4, y: 1.35, w: 3.8, h: 0.3, margin: 0,
    fontSize: 16, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });

  const fast = ["改 Python 参数", "仿真里秒级验证", "不满意立即重试"];
  fast.forEach((s, i) => {
    const y = 1.9 + i * 0.85;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 5.4, y: y, w: 3.85, h: 0.62, fill: { color: theme.bg }, rectRadius: 0.08
    });
    slide.addText(s, {
      x: 5.4, y: y, w: 3.85, h: 0.62, margin: 0, align: "center", valign: "middle",
      fontSize: 13, color: theme.primary, fontFace: "Microsoft YaHei"
    });
  });

  slide.addText("关键: 跑的不是仿真控制器, 而是能烧进板子的那份真实固件", {
    x: 5.4, y: 4.28, w: 3.9, h: 0.32, margin: 0,
    fontSize: 10.5, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });

  // page badge
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("02", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };