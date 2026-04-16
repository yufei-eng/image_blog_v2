# Image Blog & Life Comic — Agent Guidelines

## Project Overview

两个 Cursor/Claude Skill：**photo-blog**（照片博客）和 **life-comic**（生活漫画），基于 Gemini 3 Pro（理解）+ Gemini 3.1 Flash Image（生成）。

- **语言**: Python 3
- **依赖**: `google-genai`, `Pillow`, `Playwright`（截图用）
- **模型**: Gemini 3 Pro（图片分析/打分）, Gemini 3.1 Flash Image（漫画生成）

## Build & Run

```bash
# 安装
bash install.sh

# 更新
bash update.sh

# 运行 photo-blog
python3 skills/photo-blog/main.py <image_paths> [--theme THEME] [--max-highlights N] [--format all]

# 运行 life-comic
python3 skills/life-comic/main.py <image_paths> [--theme THEME] [--panels N] [--format all]
```

## Directory Structure

```
image_blog/
├── install.sh                    # 安装脚本（创建 symlinks 到 ~/.claude/skills/）
├── update.sh                     # 更新脚本
├── skills/
│   ├── photo-blog/
│   │   ├── SKILL.md              # Skill 描述文件
│   │   ├── main.py               # CLI 入口
│   │   ├── photo_analyzer.py     # Gemini 图片分析/打分
│   │   ├── blog_generator.py     # 博客内容生成
│   │   ├── html_renderer.py      # HTML 输出
│   │   ├── png_renderer.py       # HiDPI PNG 输出（Playwright）
│   │   ├── config.json.example   # 配置模板
│   │   └── requirements.txt
│   └── life-comic/
│       ├── SKILL.md
│       ├── main.py
│       ├── photo_analyzer.py
│       ├── comic_generator.py    # Gemini 漫画生成
│       ├── html_renderer.py
│       ├── png_renderer.py
│       ├── config.json.example
│       └── requirements.txt
└── README.md
```

## Key Patterns

- **Triple Output**: 每次生成同时产出 HTML + Markdown + PNG
- **HiDPI PNG**: 通过 Playwright 截图 HTML 页面，2x 缩放
- **图片分析**: Gemini 3 Pro 打分（0-100），多维度评估
- **多样性优化**: 选图时避免重复场景，覆盖不同时间/地点
- **Config**: `config.json` 存放 `COMPASS_CLIENT_TOKEN`，不提交到 Git

## Code Conventions

- Skill 源文件**纯英文**，不含中文字符
- 运行时根据用户语言输出对应语言内容
- 不向用户暴露 template_id 等内部字段
- 错误时给出有帮助的提示（如"建议用 --theme 指定主题"）

## Delivery Rules

- 聊天中展示 **rich text** 版本
- PNG 和 HTML 以**下载链接**形式提供，不 inline
- HTML 链接标签做国际化（"for internal testing" / 对应语言）
- 生成后建议用户尝试另一种格式（blog ↔ comic）
