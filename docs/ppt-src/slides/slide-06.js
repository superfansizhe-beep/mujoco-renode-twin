// 06 · Parameter single-source-of-truth (fwconfig gate) - process
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("参数单一数据源,机器保证不失配", {
    x: 0.5, y: 0.4, w: 9, h: 0.55, margin: 0,
    fontSize: 30, color: theme.primary, bold: true, fontFace: "Microsoft YaHei", fit: "shrink"
  });
  slide.addText("这是孪生能成立的基础: C 固件与 Python 仿真永远用同一套参数", {
    x: 0.5, y: 0.98, w: 9, h: 0.3, margin: 0,
    fontSize: 13, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // pipeline
  const pipe = [
    ["Python 参数", "唯一数据源", theme.primary],
    ["race_fwconfig.h", "自动生成的 C 头文件", theme.accent],
    ["race_fw.elf", "交叉编译产物", theme.secondary],
    ["Renode 执行", "真实固件行为", theme.primary]
  ];
  pipe.forEach((p, i) => {
    const x = 0.5 + i * 2.4;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: 1.5, w: 1.95, h: 1.05, fill: { color: theme.light }, rectRadius: 0.09
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: 1.5, w: 1.95, h: 0.07, fill: { color: p[2] }
    });
    slide.addText(p[0], {
      x: x + 0.12, y: 1.68, w: 1.7, h: 0.3, margin: 0,
      fontSize: 13, color: theme.primary, bold: true, fit: "shrink",
      // CJK labels must not be set in the Latin-only mono face
      fontFace: /[一-鿿]/.test(p[0]) ? "Microsoft YaHei" : "Consolas"
    });
    slide.addText(p[1], {
      x: x + 0.12, y: 2.02, w: 1.7, h: 0.45, margin: 0,
      fontSize: 10, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
    if (i < 3) {
      slide.addText(">", {
        x: x + 1.95, y: 1.85, w: 0.45, h: 0.35, margin: 0, align: "center", valign: "middle",
        fontSize: 18, color: theme.accent, bold: true, fontFace: "Arial"
      });
    }
  });

  // the gate
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 2.85, w: 9.0, h: 1.0, fill: { color: theme.primary }, rectRadius: 0.09
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 2.85, w: 0.09, h: 1.0, fill: { color: theme.accent }
  });
  slide.addText("--check 门", {
    x: 0.78, y: 3.0, w: 2.4, h: 0.3, margin: 0,
    fontSize: 15, color: theme.accent, bold: true, fontFace: "Consolas"
  });
  slide.addText("手改了 .h 或改了 Python 忘同步 -> 直接 exit 1 报错", {
    x: 0.78, y: 3.34, w: 5.2, h: 0.32, margin: 0,
    fontSize: 13, color: "FFFFFF", fontFace: "Microsoft YaHei"
  });
  slide.addText("uv run python -m race.fwconfig --check", {
    x: 6.0, y: 3.05, w: 3.3, h: 0.28, margin: 0, valign: "middle",
    fontSize: 9.5, color: theme.light, fontFace: "Consolas"
  });
  slide.addText("实测 exit 0 (参数同步)", {
    x: 6.0, y: 3.33, w: 3.3, h: 0.26, margin: 0, valign: "middle",
    fontSize: 9.5, color: theme.light, fontFace: "Microsoft YaHei"
  });

  // provenance
  slide.addText("每个物理常量都标注来源 (bot/mass_properties.py, 21 处)", {
    x: 0.5, y: 4.05, w: 9, h: 0.3, margin: 0,
    fontSize: 14, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  const tags = [
    ["CITE", "8", "有公开来源可查"],
    ["CALC", "7", "CAD 体积 x 密度"],
    ["WEIGH", "3", "待上秤实测"],
    ["GUESS", "3", "占位, 明确是猜的"]
  ];
  tags.forEach((t, i) => {
    const x = 0.5 + i * 2.3;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: 4.45, w: 1.9, h: 0.75, fill: { color: theme.light }, rectRadius: 0.07
    });
    slide.addText(t[0], {
      x: x + 0.12, y: 4.53, w: 1.2, h: 0.26, margin: 0,
      fontSize: 12, color: theme.accent, bold: true, fontFace: "Consolas"
    });
    slide.addText(t[1], {
      x: x + 1.55, y: 4.5, w: 0.5, h: 0.3, margin: 0, align: "right",
      fontSize: 15, color: theme.primary, bold: true, fontFace: "Arial"
    });
    slide.addText(t[2], {
      x: x + 0.12, y: 4.82, w: 1.7, h: 0.28, margin: 0,
      fontSize: 9, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("06", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };