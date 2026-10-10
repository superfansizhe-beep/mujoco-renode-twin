// 04 · Three controller slots (core mechanism) - comparison
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("核心机制: 三个可互换的控制器槽", {
    x: 0.5, y: 0.4, w: 9, h: 0.55, margin: 0,
    fontSize: 30, color: theme.primary, bold: true, fontFace: "Microsoft YaHei", fit: "shrink"
  });
  slide.addText("物理侧完全不变, 三者走同一个接口  controller.step(sensor) -> motor", {
    x: 0.5, y: 0.98, w: 9, h: 0.3, margin: 0,
    fontSize: 13, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  const cols = [
    ["stub", "Python 桩", "快速验证环境是否通畅", "秒", false],
    ["hostc", "宿主 C 库", "日常调参, 最快, 无需交叉编译", "秒", true],
    ["renode", "真实固件 ELF", "验证烧到车上就是这个行为", "分钟", false]
  ];

  cols.forEach((c, i) => {
    const x = 0.5 + i * 3.1;
    const h = 2.75;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: 1.45, w: 2.85, h: h,
      fill: { color: c[4] ? theme.primary : theme.light },
      rectRadius: 0.1
    });
    slide.addText(c[0], {
      x: x + 0.2, y: 1.6, w: 2.45, h: 0.35, margin: 0,
      fontSize: 20, color: theme.accent, bold: true, fontFace: "Consolas"
    });
    slide.addText(c[1], {
      x: x + 0.2, y: 2.0, w: 2.45, h: 0.3, margin: 0,
      fontSize: 14, color: c[4] ? "FFFFFF" : theme.primary, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(c[2], {
      x: x + 0.2, y: 2.42, w: 2.45, h: 0.75, margin: 0,
      fontSize: 11, color: c[4] ? theme.light : theme.secondary, fontFace: "Microsoft YaHei"
    });
    slide.addShape(pres.shapes.LINE, {
      x: x + 0.2, y: 3.3, w: 2.45, h: 0,
      line: { color: theme.secondary, width: 0.75 }
    });
    slide.addText("迭代 " + c[3], {
      x: x + 0.2, y: 3.45, w: 2.45, h: 0.3, margin: 0,
      fontSize: 11, color: c[4] ? theme.accent : theme.secondary, bold: true, fontFace: "Microsoft YaHei"
    });
  });

  // payoff callout
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.42, w: 8.6, h: 0.85, fill: { color: theme.accent }, rectRadius: 0.08
  });
  slide.addText("parity-gated: 三槽同接口, 同一场景跑三份, 输出曲线逐点一致", {
    x: 0.75, y: 4.55, w: 8.1, h: 0.32, margin: 0,
    fontSize: 15, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("这就证明了: 电脑上调的参数 = 真车行为", {
    x: 0.75, y: 4.88, w: 8.1, h: 0.3, margin: 0,
    fontSize: 13, color: "FFFFFF", fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("04", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };