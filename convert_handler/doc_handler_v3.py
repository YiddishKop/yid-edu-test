import os
import uuid
import re
from pathlib import Path
from docx import Document
from PIL import Image
from wand.image import Image as WandImage

# =========================
# 配置输出目录
# =========================
INPUT_DOCX = "2222.docx"  # 要处理的 Word 文件
OUTPUT_FOLDER = "word_md_parts"
IMAGES_SUBFOLDER = "images"

Path(OUTPUT_FOLDER, IMAGES_SUBFOLDER).mkdir(parents=True, exist_ok=True)

# =========================
# ✅ 新增：提取含下划线 run 的文本
# =========================
def extract_text_with_underline(paragraph):
    parts = []
    for run in paragraph.runs:
        txt = run.text

        # 情况1：下划线样式 + 空内容
        if (not txt.strip()) and run.font.underline:
            parts.append("_____")
            continue

        # 情况2：run.text 本身含 "_" 字符
        if "_" in txt:
            parts.append(txt.replace("_", "_____"))
            continue

        # 情况3：普通文本
        parts.append(txt)

    return "".join(parts).strip()

# =========================
# 工具函数：保存图片 (保持你的原逻辑)
# =========================
def save_image(image_bytes, ext):
    img_uuid = f"{uuid.uuid4().hex}.png"  # 默认转 PNG
    out_path = os.path.join(OUTPUT_FOLDER, IMAGES_SUBFOLDER, img_uuid)

    if ext.lower() in ["emf", "wmf"]:
        with WandImage(blob=image_bytes) as img:
            img.format = "png"
            img.save(filename=out_path)
    else:
        with open(out_path, "wb") as f:
            f.write(image_bytes)

    return os.path.join(IMAGES_SUBFOLDER, img_uuid)

# =========================
# ✅ 修改 parse_docx：替换 para.text.strip()
# =========================
def parse_docx(docx_path):
    doc = Document(docx_path)
    parts = []

    current_text = ""
    current_images = []

    # ✅ 修正后的正则表达式，支持 【例1】 格式
    pattern = re.compile(
        r'(?m)^\s*'
        r'(?:'
        r'\d+[．.]|\d+[)]|'         # 匹配 1. 或 1)
        r'【例\d+】|【练习\d+】|【变式\d*-*\d*】|' # 2. 【例1】 这种带方括号的格式
        r'例\d+|练习\d+|变式\d+'     # 匹配 例1, 练习1 等
        r')\s*'
    )
    def flush_current():
        nonlocal current_text, current_images
        if current_text.strip():
            md_text = current_text
            for img_path in current_images:
                md_text += f"\n\n![image]({img_path})"
            parts.append(md_text.strip())

        current_text = ""
        current_images = []

    # ✅ ✅ 核心修改：替代 para.text.strip() 为 extract_text_with_underline()
    for para in doc.paragraphs:
        text = extract_text_with_underline(para)
        if not text:
            continue

        if pattern.match(text):
            flush_current()
            current_text += text + "\n"
        else:
            current_text += text + "\n"

    flush_current()

    # ✅ 保留你原先的图片提取逻辑
    for rel in doc.part._rels:
        rel_obj = doc.part._rels[rel]
        if "image" in rel_obj.target_ref:
            img_bytes = rel_obj.target_part.blob
            ext = Path(rel_obj.target_ref).suffix.lstrip(".")
            img_path = save_image(img_bytes, ext)
            if parts:
                parts[-1] += f"\n\n![image]({img_path})"

    return parts

# =========================
# 主流程：生成 Markdown 文件
# =========================
def save_parts_to_md(parts):
    for i, part in enumerate(parts, 1):
        md_filename = os.path.join(OUTPUT_FOLDER, f"word_part_{i}.md")
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(part)
    print(f"生成 {len(parts)} 个 Markdown 文件到 {OUTPUT_FOLDER} 文件夹。")

# =========================
# 执行
# =========================
if __name__ == "__main__":
    md_parts = parse_docx(INPUT_DOCX)
    save_parts_to_md(md_parts)
