# 右侧页面级滚动布局说明

本文档用于说明当前右侧区域的三段式布局与可调参数位置，便于后续维护。

## 布局结构

右侧区域分为三块，互斥不叠加：

1. 顶部导航栏（固定）
2. 中间消息区（页面级主滚动）
3. 底部输入区（固定层，父区域透明、输入框本体不透明）

为了避免固定输入区遮挡消息区，页面在内容末尾保留了一个透明占位区：

- 占位区类名：`composer-region`
- 固定输入层类名：`composer-fixed-layer`

对应代码：

- `src/pages/ChatPage.tsx`
- `src/styles/index.css`
- `src/styles/theme.css`

## 常用微调变量（`src/styles/theme.css`）

1. 左右边界：

- `--right-scroll-boundary-left`
- `--right-scroll-boundary-right`

2. 内容最大宽度：

- `--right-content-max-width`

3. 顶部与底部间距：

- `--right-content-top-gap`
- `--chat-bottom-gap`
- `--composer-region-reserved-height`
- `--composer-bottom-note-height`
- `--composer-bottom-note-font-size`

4. 回到底部按钮：

- `--scroll-bottom-threshold`
- `--scroll-bottom-button-vertical-ratio`

5. 助手回复字体样式：

- `--assistant-response-font-size`
- `--assistant-response-line-height`
- `--assistant-response-font-family`
- `--assistant-response-font-weight`
- `--assistant-response-letter-spacing`
- `--assistant-response-paragraph-gap`

## 调整建议

1. 先固定 `--right-content-max-width`，再调整左右边界。  
2. 如果最后一条消息和输入区距离过近，优先调大 `--chat-bottom-gap`。  
3. 如果消息被输入区遮挡，优先调大 `--composer-region-reserved-height`。  
4. 如果底部提示区高度不合适，调整 `--composer-bottom-note-height`。  
5. 如果“回到底部”按钮过早/过晚隐藏，调整 `--scroll-bottom-threshold`。
