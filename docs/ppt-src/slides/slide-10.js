// 10 · Summary / closing
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.16, h: 5.625, fill: { color: theme.accent }
  });

  slide.addText("小结", {
    x: 0.6, y: 0.5, w: 5, h: 0.6, margin: 0,
    fontSize: 34, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("物理是真的, 固件是真的, 参数不会失配", {
    x: 0.6, y: 1.12, w: 6.5, h: 0.32, margin: 0,
    fontSize: 14, color: theme.accent, fontFace: "Microsoft YaHei"
  });

  const takeaways = [
    ["真实固件在环", "Renode 执行的就是能烧板子的那份 ELF, 不是替身"],
    ["三槽同接口可对比", "逐点一致即证明电脑上调的参数等于真车行为"],
    ["参数机器保证不失配", "fwconfig --check 门 + 21 处来源标注"],
    ["四任务全部通过", "停车误差 < 6 cm, 零摔倒"]
  ];

  takeaways.forEach((t, i) => {
    const y = 1.7 + i * 0.78;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: y, w: 6.1, h: 0.66, fill: { color: theme.bg }, rectRadius: 0.07
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: y, w: 0.07, h: 0.66, fill: { color: theme.accent }
    });
    slide.addText(t[0], {
      x: 0.82, y: y + 0.07, w: 2.35, h: 0.28, margin: 0,
      fontSize: 13, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(t[1], {
      x: 0.82, y: y + 0.36, w: 5.7, h: 0.26, margin: 0,
      fontSize: 10, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
  });

  // right panel
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 7.1, y: 1.7, w: 2.4, h: 3.0, fill: { color: theme.accent }, rectRadius: 0.1
  });
  slide.addText("现场演示", {
    x: 7.3, y: 1.9, w: 2.0, h: 0.3, margin: 0,
    fontSize: 14, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("git clone\nuv sync\nbash tools/fetch_vendor.sh\nuv run python -m race --all\nbash tools/demo.sh", {
    x: 7.3, y: 2.3, w: 2.05, h: 1.6, margin: 0,
    fontSize: 8.5, color: "FFFFFF", fontFace: "Consolas", lineSpacing: 15
  });
  slide.addText("MIT License", {
    x: 7.3, y: 4.3, w: 2.0, h: 0.28, margin: 0,
    fontSize: 10, color: "FFFFFF", fontFace: "Arial"
  });

  slide.addText("github.com/rim5432/mujoco-renode-twin", {
    x: 0.6, y: 5.0, w: 6, h: 0.3, margin: 0,
    fontSize: 11, color: theme.light, fontFace: "Arial"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.accent }, rectRadius: 0.05
  });
  slide.addText("12", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: "FFFFFF", fontFace: "Arial"
  });
}
module.exports = { createSlide };