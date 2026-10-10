// 03 · Architecture (three layers)
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("三层架构", {
    x: 0.5, y: 0.4, w: 9, h: 0.55, margin: 0,
    fontSize: 30, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("物理侧永远不变, 大脑可插, 数据每 5ms 交互一次", {
    x: 0.5, y: 0.98, w: 9, h: 0.3, margin: 0,
    fontSize: 13, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  const layers = [
    ["MuJoCo 物理引擎", "车的身体", "算重力 / 摩擦 / 电机扭矩, 200Hz 推进", theme.primary],
    ["控制器 (三选一)", "车的大脑", "只拿原始传感器, 只输出电机占空比", theme.accent],
    ["three.js 查看器", "你的眼睛", "浏览器里 3D 实时观察, 30Hz 状态帧", theme.secondary]
  ];

  layers.forEach((L, i) => {
    const y = 1.45 + i * 1.15;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y: y, w: 6.15, h: 0.95, fill: { color: theme.light }, rectRadius: 0.1
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y: y, w: 0.09, h: 0.95, fill: { color: L[3] }
    });
    slide.addText(L[0], {
      x: 0.75, y: y + 0.12, w: 2.6, h: 0.3, margin: 0,
      fontSize: 15, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(L[1], {
      x: 0.75, y: y + 0.47, w: 2.6, h: 0.3, margin: 0,
      fontSize: 11, color: L[3], fontFace: "Microsoft YaHei"
    });
    slide.addText(L[2], {
      x: 3.4, y: y + 0.22, w: 3.1, h: 0.55, margin: 0, valign: "middle",
      fontSize: 11, color: theme.secondary, fontFace: "Microsoft YaHei"
    });

    if (i < 2) {
      // keep clear of the right panel (starts at x=6.85)
      slide.addText("5 ms", {
        x: 6.42, y: y + 0.3, w: 0.4, h: 0.3, margin: 0, align: "right",
        fontSize: 9, color: theme.accent, bold: true, fontFace: "Consolas"
      });
    }
  });

  // right: why 5ms
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.85, y: 1.45, w: 2.65, h: 3.3, fill: { color: theme.primary }, rectRadius: 0.1
  });
  slide.addText("为什么是 5 ms", {
    x: 7.05, y: 1.65, w: 2.3, h: 0.3, margin: 0,
    fontSize: 14, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("真车 IMU 输出速率就是 200 Hz", {
    x: 7.05, y: 2.1, w: 2.3, h: 0.6, margin: 0,
    fontSize: 12, color: theme.light, fontFace: "Microsoft YaHei"
  });
  slide.addShape(pres.shapes.LINE, {
    x: 7.05, y: 2.8, w: 2.25, h: 0, line: { color: theme.secondary, width: 0.75 }
  });
  slide.addText("仿真节拍必须与真硬件一致, 否则时序不真实", {
    x: 7.05, y: 2.95, w: 2.3, h: 0.9, margin: 0,
    fontSize: 12, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("车歪超过 55 度强制输出 0, 防翻车疯转", {
    x: 7.05, y: 4.05, w: 2.3, h: 0.55, margin: 0,
    fontSize: 10, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("03", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };