// 09 · Engineering scale & test status - data
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("工程规模与测试状态", {
    x: 0.5, y: 0.4, w: 9, h: 0.55, margin: 0,
    fontSize: 30, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("代码量", {
    x: 0.5, y: 1.15, w: 4.5, h: 0.3, margin: 0,
    fontSize: 15, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  // stat callouts
  const stats = [
    ["12,844", "Python 行数", "80 个文件"],
    ["48", "C 固件文件", "交叉编译至 F407"],
    ["9", "自研 C# 外设模型", "Renode 侧"],
    ["236", "个测试用例", "23 个测试文件"]
  ];
  stats.forEach((s, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.5 + col * 2.35, y = 1.55 + row * 1.25;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: y, w: 2.2, h: 1.1, fill: { color: theme.light }, rectRadius: 0.09
    });
    slide.addText(s[0], {
      x: x + 0.15, y: y + 0.12, w: 1.9, h: 0.5, margin: 0,
      fontSize: 26, color: theme.accent, bold: true, fontFace: "Arial", fit: "shrink"
    });
    slide.addText(s[1], {
      x: x + 0.15, y: y + 0.62, w: 1.9, h: 0.26, margin: 0,
      fontSize: 11, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(s[2], {
      x: x + 0.15, y: y + 0.86, w: 1.9, h: 0.22, margin: 0,
      fontSize: 9, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
  });

  // test status
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.35, y: 1.15, w: 4.15, h: 3.4, fill: { color: theme.primary }, rectRadius: 0.1
  });
  slide.addText("测试现状", {
    x: 5.6, y: 1.35, w: 3.7, h: 0.3, margin: 0,
    fontSize: 15, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });

  const bars = [
    ["通过 passed", 227, 3.46],
    ["跳过 skipped", 9, 0.14],
    ["失败 failed", 0, 0.02]
  ];
  bars.forEach((b, i) => {
    const y = 1.85 + i * 0.62;
    slide.addText(b[0], {
      x: 5.6, y: y, w: 3.7, h: 0.24, margin: 0,
      fontSize: 10, color: theme.light, fontFace: "Microsoft YaHei"
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 5.6, y: y + 0.26, w: 3.6, h: 0.18, fill: { color: theme.bg }, rectRadius: 0.03
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 5.6, y: y + 0.26, w: b[2], h: 0.18,
      fill: { color: i === 0 ? theme.accent : (i === 1 ? theme.secondary : "FFFFFF") },
      rectRadius: 0.03
    });
    slide.addText(String(b[1]), {
      x: 8.7, y: y, w: 0.5, h: 0.24, margin: 0, align: "right",
      fontSize: 11, color: "FFFFFF", bold: true, fontFace: "Arial"
    });
  });

  slide.addShape(pres.shapes.LINE, {
    x: 5.6, y: 3.85, w: 3.65, h: 0, line: { color: theme.secondary, width: 0.75 }
  });
  slide.addText("零失败 · 227 项通过", {
    x: 5.6, y: 3.93, w: 3.7, h: 0.26, margin: 0,
    fontSize: 12, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("pytest 收集 236 例(含 subtests 展开); 9 项跳过为可选外部依赖(GrabCAD 登录下载等)", {
    x: 5.6, y: 4.18, w: 3.7, h: 0.42, margin: 0,
    fontSize: 8.5, color: theme.light, fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("11", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };