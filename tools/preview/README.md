# 小程序 Web 预览（开发期用）

**在浏览器里直接看、直接点真实的小程序页面** —— 读的是 `miniprogram/` 下的原始文件，
连的是真实后端。改页面不用同步改预览，刷新即生效。

## 为什么需要它

微信小程序的运行时是微信客户端私有的（渲染层 + `wx.*` 原生能力 + 私有编译链），
**浏览器里跑不起真正的小程序**，官方路径只有微信开发者工具。
但「开发期看页面 + 看真实数据 + 点交互」这件事可以在浏览器里做到：

- WXML 用一个小型解释层渲染成 HTML（`runner.js`）
- WXSS 里 `rpx` 换算成 `calc(N * var(--rpx))`，`page` 选择器映射到 `.wb-page-root`
- `Page()` / `App()` / `wx.*` / `getApp()` 用 stub 顶掉，**页面 JS 真的在浏览器里跑**
- `wx.request` 走 `fetch` 打真实后端

**单源原则**：本目录不复制任何页面的结构或样式，读的就是 `miniprogram/` 原始文件。
所以不会有「预览和真机两套代码互相漂移」的问题。

**不覆盖的部分**（这些仍要去开发者工具 / 真机验）：
`wx.*` 原生能力全集、原生组件（picker/switch）的真实交互、真机渲染差异、
分包 / 插件 / 云能力、审核相关行为、分享的实际发出（预览里只打印分享文案）。

## 启动

两个终端（或两个后台任务）：

```bash
# 1) 后端
venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) 预览服务
venv/bin/python tools/preview/serve.py            # 默认 :8899
```

然后打开 <http://localhost:8899/>（**用 `localhost`，不要用 `127.0.0.1`** ——
这台机器上代理策略按主机名区分，`127.0.0.1` 会被拦成空响应）。

页面下拉可直达任意页；「跑通起名流程」按钮会**走真实 UI** 把
资料页 → 感觉页 → 结果页跑一遍（结果页/详情页依赖 `globalData.lastResult`，
直接跳过去会被页面自己的 `navigateBack` 弹回）。

URL 参数（便于分享/自动化）：

| 参数 | 作用 |
| --- | --- |
| `?page=pages/result/result` | 直达某页（缺上下文时会先自动跑一遍对应流程） |
| `?flow=1` / `?flow=prenatal` / `?flow=analyze` / `?flow=detail` | 跑通起名 / 孕期 / 测评 / 起名+详情 流程 |
| `?surname=林&birth=1994-05-20` | 给流程喂入参 |
| `?logs=0` | 隐藏日志侧栏 |

## 自检探针（不靠肉眼判定预览是否正常）

```bash
# 起一只常驻无头 Chrome（推荐：一次起好，反复巡检）
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --remote-debugging-port=9222 --remote-allow-origins=* \
  --no-first-run --no-sandbox --disable-gpu --use-angle=swiftshader \
  --user-data-dir=/tmp/mingtang-chrome-live about:blank &

# 巡检常用页 + 跑通起名流程
node tools/preview/probe.js --attach 9222 --flow

# 名字本专项：起名落盘 → 收藏 → 名字本 → 恢复 → 删除 → 清空
node tools/preview/probe.js --attach 9222 --book

# 自绘日期弹层专项：日期行 → 三列滚选 → 回填，以及十二时辰格与八字开关联动
node tools/preview/probe.js --attach 9222 --picker

# 输入框专项：点击不误派发 → 真实键入 → 焦点保持
node tools/preview/probe.js --attach 9222 --input

# 只看一页 / 全部页
node tools/preview/probe.js --attach 9222 pages/detail/detail
node tools/preview/probe.js --attach 9222 --all
```

输出每页的：是否到达、处理器数量、控制台报错、面板异常、可见文本、截图（`/tmp/mingtang-shots/`）。
退出码非 0 即有硬报错，可以挂进 CI 或当提交前自检。

不加 `--attach` 时探针会自己起 Chrome（`--remote-debugging-port=0`，失败自动重试），
但本机沙箱下 Chrome 冷启动慢且偶发起不来，**推荐 `--attach`**。

## 文件

| 文件 | 作用 |
| --- | --- |
| `serve.py` | 清单服务：`/` 外壳、`/runner.js`、`/__manifest`（全部源文件原文）、`/mp/*`（图片等静态资源） |
| `runner.js` | 运行时：WXML 解析渲染、表达式求值、WXSS 转换、`Page/App/wx` stub、页面栈 |
| `index.html` | 外壳：手机壳 + 页面下拉 + 日志侧栏 + 流程自动化接口（`window.__wb`） |
| `probe.js` | 自检探针：逐页巡检 + 截图 + 退出码判定 |

## 已知取舍

- **渲染是增量补丁（morph），不是整块替换**。这是必须的，别改回去：
  旧实现每次 `setData` 都 `mount.innerHTML = html`，会把**正在输入的 input 一起删掉**，
  中文输入法（IME）的组字状态挂在那个 DOM 节点上，节点一换组字就断，
  表现是「一个字都打不进去」。现在同标签就地改属性、不同标签才替换，
  并且**对获得焦点的输入框跳过 `value` 属性**（交给浏览器持有）。
  同时顺带保住了滚动位置与文本选区。
- **点击只派发 `tap` / `longpress`，不派发 `bindinput` / `bindchange`**。
  `data-wb-ev` 只表示「这个元素挂了某个事件」，不代表它是点击 ——
  `<input bindinput>` 也带这个属性。旧实现点击就派发、`detail` 是 `{}`，
  页面里 `e.detail.value` 为 `undefined` → `setData({surname: undefined})` → 整页重绘
  → 输入框被换掉 → 点一下就失焦。（`picker` / `switch` 是替身，在类型判断之前单独处理。）

- **`<picker>` 在预览里点不开，页面已全部改成自绘**：日期（三列 `scroll-view`）
  与时辰（单列）共用同一套底部弹层（`utils/date-sheet.js` / `utils/hours.js`
  + `app.wxss` 里的 `.sheet-*`），行业等多选项用可点标签。
  预览器仍保留 `<picker>` 替身（映射到原生 `select`/`date`），但**不要再往页面里加** ——
  `tests/test_profile_page.py` 里有一条测试会扫全站 wxml。
- **浮层样式一律写在 `app.wxss`，不要放进页面再 `@import`**：日期弹层与时辰下拉
  全靠 `position: fixed` 撑着，样式少加载一次就会掉回文档流 —— 表现是「点了没反应，
  页面底部多出一长串年份」，很容易被当成交互 bug 查半天。`app.wxss` 每页必加载，
  没有这层不确定性。（`transformWxss` 仍会内联 `@import`，留作兜底。）
- **`scroll-view` 的鼠标拖拽是预览器补的**：桌面浏览器不会因为按住拖动而滚动，
  而预览是手机形态，用户会下意识往上拖 —— 反馈就是「列表滚不动」。
  `index.html` 的 `enableDragScroll()` 兜住这件事（拖超 4px 会吞掉随后的 click，
  免得松手误选中一项）。真机本来就支持触摸滚动，不依赖它。
- **手机壳高度跟窗口走**（`height: calc(100vh - 96px)`）：原先写死 760px，
  窗口一矮手机壳就高出可视区，底部弹层落到屏幕外，看着同样像「打不开 / 滚不动」。
- **`scroll-into-view` 需要预览器自己实现**：它是微信原生能力，浏览器没有。
  日期弹层的年/月/日三列靠它滚到当前选中项，不实现就会停在 1900 年，
  用户得往下翻一百多行。见 `index.html` 的 `applyScrollIntoView()`。
- **`wx.request` 的 `timeout` 在替身里不生效**（走的是 `fetch`，没有超时）。
  页面对超时不能只依赖宿主：`utils/api.js` 的探活自带 1500ms 兜底定时器。
- **`position: fixed` 在预览里相对整个浏览器窗口，不是手机壳**：日期弹层的遮罩会
  铺满整个预览区（真机与开发者工具里只有设备宽）。判定弹层「能不能开、能不能选、
  能不能回填」以探针 `--picker` 为准，别以截图里的宽度为准。
- **后台页面的 setData 只更新数据、不重绘**（与真机一致）。这是刻意做的：
  感觉页 `onSubmit` 的 `finally { setData({loading:false}) }` 在 `navigateTo` 之后执行，
  若允许它重绘，会把已打开的结果页画面覆盖回感觉页。
- **页面实例保活**：`navigateTo` 建新实例，`navigateBack` 复用栈里的实例，
  所以「结果页筛完 → 返回 → 再进来」的状态保持与真机一致。
- `reLaunch` / `switchTab`（`reset`）会销毁全部实例，`redirectTo`（`replace`）销毁当前实例。
- **`wx.showModal` 是浏览器替身**：自绘确认弹层。自动化跑流程时用
  `window.__wb.setModalAnswer(true|false)` 预设答案，否则脚本会停在弹窗上等真人点。
- **本地存储用内存对象替身**（`wx.setStorageSync` 系列），刷新即清空，与真机一致的地方是
  「退出小程序就丢」这一层语义；真机还有 10MB 配额，预览里不模拟。
  用 `window.__wb.storage('<key>')` 可以直接读到落盘内容做断言。
