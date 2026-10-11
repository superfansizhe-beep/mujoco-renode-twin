# 答辩 PPT 构建源

`docs/mujoco-renode-twin-defense.pptx` 的可重建源文件。交付的 `.pptx` 已经生成好并提交,
这个目录只是让你(以及未来的你)能改内容后重新生成,不用从零写。

## 重新生成

```bash
cd docs/ppt-src
npm install          # 只依赖 pptxgenjs
node slides/compile.js
# 产物: slides/output/mujoco-renode-twin-defense.pptx
```

## 目录

| 路径 | 说明 |
|---|---|
| `slides/compile.js` | 入口。定义 16:9 版式、配色 theme、12 页的拼接顺序 |
| `slides/slide-01.js` | 封面 |
| `slides/slide-02.js` | 为什么做数字孪生 |
| `slides/slide-03.js` | 三层架构 |
| `slides/slide-04.js` | 三个控制器槽 |
| `slides/slide-05.js` | 固件在环 + 9 个 C# 外设模型 |
| `slides/slide-06.js` | 参数单一数据源 + provenance |
| `slides/slide-06b.js` | CAD 建模(build123d / GrabCAD) |
| `slides/slide-07b.js` | 赛题要求原图 |
| `slides/slide-07.js` | 三层之上的数据流 |
| `slides/slide-08.js` | 3D 查看器 |
| `slides/slide-09.js` | 工程规模与测试状态 |
| `slides/slide-10.js` | 小结 |
| `assets/` | 页面用图:`task1.png` / `task2.png` / `problem.jpg` |

文件名后缀 `b` 表示后来插入的页,所以 `07b` 排在 `07` 前面;`compile.js` 里的
`order` 数组才是真正的页序。

## 改页时的几条硬规矩

1. **配色只用 `theme` 里的 5 个键**(`primary` / `secondary` / `accent` / `light` / `bg`),
   写成 6 位 hex,不带 `#`。
2. **正文标点用半角**。全角 `,。、;:()""` 在这个 deck 里会渲染成方框。
3. **页码徽章坐标固定** `x: 9.3, y: 5.1, w: 0.42, h: 0.3`,封面页不加。
4. 插页之后记得改后面每一页的页码数字,别让两个页码一样。
5. **图片文件的扩展名必须和内容一致**。踩过的坑:`task2.png` 里装的是 JPEG
   数据,pptxgenjs 按 `image/png` 写进包,条目 CRC 坏掉,PowerPoint 画一个空框
   而且不报错。`check_pptx.py` 就是为了抓这个。

## 怎么自查

```bash
node slides/compile.js
python3 check_pptx.py slides/output/mujoco-renode-twin-defense.pptx
```

`check_pptx.py` 查三件事:zip 完整性、每个 media 条目能不能读、图片的真实格式
和扩展名是否一致。任何一条不过就别发出去 —— 图片不显示的时候它是唯一会告诉你
原因的地方。

再顺手看一眼版面:

```bash
python3 -c "
from pptx import Presentation
p = Presentation('slides/output/mujoco-renode-twin-defense.pptx')
print('pages:', len(p.slides), 'ratio:', round(p.slide_width/p.slide_height, 4))
"
```

数字要跟 `docs/DEFENSE.md` 里的「数据支撑」表一致。改完测试数字,两处一起改。