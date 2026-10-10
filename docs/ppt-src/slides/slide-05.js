// 05 · Firmware in the loop (Renode + self-written C# peripheral models)
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText("固件在环: 自研 C# 外设模型", {
    x: 0.5, y: 0.4, w: 9, h: 0.55, margin: 0,
    fontSize: 30, color: theme.primary, bold: true, fontFace: "Microsoft YaHei", fit: "shrink"
  });
  slide.addText("Renode 在 PC 上模拟 STM32F407, 真实固件二进制以为自己跑在芯片上", {
    x: 0.5, y: 0.98, w: 9, h: 0.3, margin: 0,
    fontSize: 13, color: theme.secondary, fontFace: "Microsoft YaHei"
  });

  // left: the 9 models grid
  slide.addText("9 个手写外设模型", {
    x: 0.5, y: 1.45, w: 4.6, h: 0.3, margin: 0,
    fontSize: 15, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
  });

  const models = [
    ["mpu6050", "加速度计 + 陀螺仪"],
    ["enc_model", "编码器: 数圈数"],
    ["timer1", "输出PWM给电机的定时器"],
    ["uart", "串口打印日志"],
    ["adc_model", "测电池电压"],
    ["i2c_model", "I2C 总线"],
    ["gpio_model", "GPIO 电平"],
    ["iwdg", "看门狗(复位)"],
    ["rcc_model", "时钟树: 看CPU主频"]
  ];
  models.forEach((m, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = 0.5 + col * 1.62, y = 1.82 + row * 0.78;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: y, w: 1.5, h: 0.68, fill: { color: theme.light }, rectRadius: 0.06
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x, y: y, w: 0.06, h: 0.68, fill: { color: theme.accent }
    });
    slide.addText(m[0], {
      x: x + 0.14, y: y + 0.05, w: 1.3, h: 0.24, margin: 0,
      fontSize: 9, color: theme.primary, bold: true, fontFace: "Consolas"
    });
    slide.addText(m[1], {
      x: x + 0.14, y: y + 0.29, w: 1.32, h: 0.36, margin: 0,
      fontSize: 8, color: theme.secondary, fontFace: "Microsoft YaHei", lineSpacing: 9.5
    });
  });

  // right: signal path
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.55, y: 1.45, w: 3.95, h: 3.4, fill: { color: theme.primary }, rectRadius: 0.1
  });
  slide.addText("信号流向", {
    x: 5.8, y: 1.62, w: 3.5, h: 0.3, margin: 0,
    fontSize: 14, color: "FFFFFF", bold: true, fontFace: "Microsoft YaHei"
  });

  const flow = [
    ["传感器进来", "IMU / 编码器 / 循迹线"],
    ["固件自己算", "真实控制代码无感知"],
    ["寄存器出去", "TIM1 + 驱动寄存器"]
  ];
  flow.forEach((f, i) => {
    const y = 2.05 + i * 0.92;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 5.8, y: y, w: 3.45, h: 0.7, fill: { color: theme.bg }, rectRadius: 0.07
    });
    slide.addText(f[0], {
      x: 5.95, y: y + 0.08, w: 3.2, h: 0.26, margin: 0,
      fontSize: 12, color: theme.primary, bold: true, fontFace: "Microsoft YaHei"
    });
    slide.addText(f[1], {
      x: 5.95, y: y + 0.36, w: 3.2, h: 0.26, margin: 0,
      fontSize: 10, color: theme.secondary, fontFace: "Microsoft YaHei"
    });
    if (i < 2) {
      slide.addText("v", {
        x: 5.8, y: y + 0.7, w: 3.45, h: 0.22, margin: 0, align: "center", valign: "middle",
        fontSize: 11, color: theme.accent, bold: true, fontFace: "Arial"
      });
    }
  });

  slide.addText("真车接什么线, 模拟器就灌什么信号", {
    x: 5.8, y: 4.62, w: 3.45, h: 0.26, margin: 0,
    fontSize: 10.5, color: theme.accent, bold: true, fontFace: "Microsoft YaHei"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, fill: { color: theme.light }, rectRadius: 0.05
  });
  slide.addText("05", {
    x: 9.3, y: 5.1, w: 0.42, h: 0.3, margin: 0, align: "center", valign: "middle",
    fontSize: 10, color: theme.secondary, fontFace: "Arial"
  });
}
module.exports = { createSlide };