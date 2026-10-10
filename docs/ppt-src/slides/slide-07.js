// 07 · Measured results (four missions) - data
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("实测结果: 四个比赛任务全部通过", {
    x: 0.5, y: 0.4, w: 9, h: 0.55, margin: 0,
    fontSize: 30, color: theme.primary, bold: true, fontFace: "Microsoft YaHei", fit: "shrink"
  });
  slide.addText("命令: uv run python -m race --all    (hostc 后端, 全部通过摔倒检测与蜂鸣序列校验)", {
    x: 0.5, y: 0.98, w: 9, h: 0.3, margin: 0,
    fontSize: 12, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // chart: elapsed vs limit
  // NOTE: pptxgenjs 4.x expects labels as one row per series (2-D).
  slide.addChart(pres.charts.BAR,
    [{ name: "耗时 (s)", labels: [["Task 1", "Task 2", "Task 3", "Task 4"]],
       values: [4.68, 18.89, 24.57, 96.64] }],
    {
      x: 0.5, y: 1.45, w: 4.7, h: 3.05, barDir: "col",
      chartColors: [theme.accent],
      chartArea: { fill: { color: "FFFFFF" } },
      catAxisLabelColor: theme.secondary,
      valAxisLabelColor: theme.secondary,
      catAxisLabelFontFace: "Arial",
      valAxisLabelFontFace: "Arial",
      catAxisLabelFontSize: 10,
      valAxisLabelFontSize: 9,
      valGridLine: { color: "E2E8F0", size: 0.5 },
      catGridLine: { style: "none" },
      showValue: true, dataLabelPosition: "outEnd",
      dataLabelColor: theme.primary, dataLabelFontSize: 10,
      dataLabelFormatCode: "0.00",
      catAxisLineColor: theme.secondary,
      valAxisLineColor: theme.secondary,
      showLegend: false,
      barGapWidthPct: 60
    });

  slide.addText("限时内完成 (Task 4 无时限)", {
    x: 0.5, y: 4.55, w: 4.7, h: 0.28, margin: 0, align: "center",
    fontSize: 10, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // result table
  const rows = [
    ["任务", "结果", "耗时", "限时", "停车误差"],
    ["1  A->B 直线 + 停", "PASS", "4.68s", "15s", "0.02 m"],
    ["2  A->B->C->D->A", "PASS", "18.89s", "30s", "0.05 m"],
    ["3  A->C->B->D->A", "PASS", "24.57s", "40s", "0.02 m"],
    ["4  任务3路线 x4 圈", "PASS", "96.64s", "--", "0.03 m"]
  ];
  slide.addTable(rows, {
    x: 5.45, y: 1.45, w: 4.05, colW: [1.55, 0.6, 0.68, 0.52, 0.7],
    fontFace: "Microsoft YaHei", fontSize: 9.5,
    border: { pt: 0.5, color: "E2E8F0" },
    fill: { color: "FFFFFF" },
    color: theme.primary,
    rowH: 0.42, valign: "middle", margin: 0.06
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.45, y: 4.05, w: 4.05, h: 0.78, fill: { color: theme.primary }, rectRadius: 0.08
  });
  slide.addText("停车误差全部小于 6 cm", {
    x: 5.62, y: 4.16, w: 3.7, h: 0.28, margin: 0,
    fontSize: 13, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });
  slide.addText("四任务零摔倒 (fallen: false)", {
    x: 5.62, y: 4.46, w: 3.7, h: 0.28, margin: 0,
    fontSize: 11, color: "FFFFFF", fontFace: "Microsoft YaHei"
  });

  slide.addText("数据来源: race --all 实测输出", {
    x: 0.5, y: 4.95, w: 5, h: 0.25, margin: 0,
    fontSize: 9, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("09", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };