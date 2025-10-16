import fitz  # pip install PyMuPDF
import os
import re
import sys
import shutil
from pathlib import Path
from wand.image import Image as WandImage  # 需要安装 ImageMagick + wand

"""将 PDF 按题号/标签切分成 Markdown，并导出图片。

输出结构：
- 小 md：项目根目录，命名 word_part_<pdf名>_<序号>[_<标签>].md
- 图片：images/<pdf名>/ 下，尽量统一为 png。
"""

# ===============================
# 配置（路径、目录）
# ===============================
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # convert_handler 的上一级
IMAGES_SUBFOLDER = "images"

if len(sys.argv) < 2:
    print("用法: python convert_handler/pdf_handler.py <pdf文件路径>")
    sys.exit(1)

PDF_PATH = Path(sys.argv[1])
if not PDF_PATH.exists():
    print(f"错误：未找到文件: {PDF_PATH}")
    sys.exit(1)

DOC_BASE_NAME = PDF_PATH.stem
PARTS_OUTPUT_DIR = PROJECT_ROOT
IMG_DIR_PATH = PROJECT_ROOT / IMAGES_SUBFOLDER / DOC_BASE_NAME
IMG_DIR_PATH.mkdir(parents=True, exist_ok=True)

# ===============================
# 1️⃣ 打开 PDF 并提取文本 + 图片（保存到 images/<pdf名>/）
# ===============================
pages_content = []
pos_counter = 0

doc = fitz.open(str(PDF_PATH))

for page_index in range(len(doc)):
    page = doc[page_index]
    page_text = page.get_text()  # 获取页面文本
    page_images = []

    image_list = page.get_images(full=True)
    for img_idx, img in enumerate(image_list, start=1):
        xref = img[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        img_name = f"{DOC_BASE_NAME}_p{page_index+1}_{img_idx}.png"
        img_path = IMG_DIR_PATH / img_name
        try:
            with WandImage(blob=image_bytes) as wi:
                wi.format = 'png'
                wi.save(filename=str(img_path))
        except Exception:
            # 若转换失败，尝试直接写入原始字节（可能非 png），保证不阻断流程
            try:
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
            except Exception:
                continue
        page_images.append(f"{IMAGES_SUBFOLDER}/{DOC_BASE_NAME}/{img_name}")

    pages_content.append({
        'start': pos_counter,
        'end': pos_counter + len(page_text),
        'text': page_text,
        'images': page_images
    })
    pos_counter += len(page_text) + 1

# ===============================
# 2️⃣ 按 doc_handler 的规则切分文本（支持 > 前缀、答案/详解标签等）
# ===============================
all_text = "\n".join([p['text'] for p in pages_content])

label_pattern = re.compile(
    r"(?m)^\s*(?:>\s*)*"
    r"("  # 捕获用于命名的标签文本
    r"(?:"
    r"\d+[．.]|\d+[)]|"                     # 1. / 1) / 1．
    r"【例\d+】|【练习\d+】|【变式\d*-*\d*】|" # 【例1】/【练习1】/【变式1-1】
    r"例\d+|练习\d+|变式\d+|"
    r"【答案】|【解析】|【详解】|【参考答案】|"
    r"答案[:：]?|解析[:：]?|详解[:：]?|参考答案[:：]?"
    r")"
    r")\s*"
)

def parse_with_positions(text: str):
    parts = []
    pos = 0
    current_start = 0
    current_label = None
    for line in text.splitlines(True):
        m = label_pattern.match(line)
        if m:
            if pos > current_start:
                parts.append({'label': current_label, 'start': current_start, 'end': pos})
            current_start = pos
            current_label = m.group(1).strip()
        pos += len(line)
    if pos > current_start:
        parts.append({'label': current_label, 'start': current_start, 'end': pos})
    for p in parts:
        p['text'] = text[p['start']:p['end']].strip()
    return parts

parts = parse_with_positions(all_text)

# ===============================
# 3️⃣ 将题目和对应图片匹配并写入 Markdown（命名与 doc_handler 一致）
# ===============================

def sanitize_label(label: str | None) -> str:
    if not label:
        return ""
    s = re.sub(r'[<>:"/\\|?*]', '', label).strip()
    m = re.fullmatch(r"(\d+)[\s．.。)）]*", s)
    if m:
        s = m.group(1)
    s = re.sub(r"\s+", "_", s)
    return s

for i, part in enumerate(parts, 1):
    part_text = part['text']
    part_start = part['start']
    part_end = part['end']

    # 匹配题目跨页的图片（按范围重叠）
    part_images = []
    for page in pages_content:
        if not (part_end <= page['start'] or part_start >= page['end']):
            part_images.extend(page['images'])

    # 插入图片 Markdown（使用根目录相对路径 images/<pdf名>/...）
    for img_rel in part_images:
        part_text += f"\n\n![image]({img_rel})\n"

    # 生成文件名并保存到项目根目录
    label_fragment = sanitize_label(part.get('label'))
    if label_fragment:
        filename = PARTS_OUTPUT_DIR / f"word_part_{DOC_BASE_NAME}_{i}_{label_fragment}.md"
    else:
        filename = PARTS_OUTPUT_DIR / f"word_part_{DOC_BASE_NAME}_{i}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(part_text)

print(f"✅ PDF 按题号/标签切分完成。小 md 输出到: {PARTS_OUTPUT_DIR}")
print(f"✅ 图片已导出到: {IMG_DIR_PATH}")
