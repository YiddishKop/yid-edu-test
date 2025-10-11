import os
import uuid
import re
import io
from pathlib import Path
from docx import Document
from PIL import Image
from wand.image import Image as WandImage

# =========================
# 配置输出目录
# =========================
INPUT_DOCX = "1111.docx"  # 要处理的 Word 文件
OUTPUT_FOLDER = "word_md_parts"
IMAGES_SUBFOLDER = "images"

Path(OUTPUT_FOLDER, IMAGES_SUBFOLDER).mkdir(parents=True, exist_ok=True)

# =========================
# 工具函数：保存图片
# =========================
def save_image(image_bytes, ext):
    """
    保存图片，EMF/WMF 转 PNG，其余原样保存
    返回保存的文件名（相对路径）
    """
    img_uuid = f"{uuid.uuid4().hex}.png"  # 默认转换成 PNG
    out_path = os.path.join(OUTPUT_FOLDER, IMAGES_SUBFOLDER, img_uuid)

    if ext.lower() in ["emf", "wmf"]:
        # 转换为 PNG
        with WandImage(blob=image_bytes) as img:
            img.format = "png"
            img.save(filename=out_path)
    else:
        # PNG/JPG 等直接保存
        with open(out_path, "wb") as f:
            f.write(image_bytes)
    return os.path.join(IMAGES_SUBFOLDER, img_uuid)

# =========================
# 工具函数：提取 Word 文本 + 图片 + 公式
# =========================
def parse_docx(docx_path):
    doc = Document(docx_path)
    parts = []

    # 遍历段落，暂存一题的内容
    current_text = ""
    current_images = []

    # 支持的题号模式
    pattern = re.compile(
        r'(?m)^\s*(?:\d+[．.]|\d+[)]|例\d+|练习\d+)\s*'
    )

    def flush_current():
        nonlocal current_text, current_images
        if current_text.strip():
            # 将图片插入 md 占位符
            md_text = current_text
            for img_path in current_images:
                md_text += f"\n\n![image]({img_path})"
            parts.append(md_text.strip())
        current_text = ""
        current_images = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        if pattern.match(text):
            # 遇到新题号，先 flush 前一题
            flush_current()
            current_text += text + "\n"
        else:
            current_text += text + "\n"

    flush_current()  # 最后一题

    # 提取图片
    for rel in doc.part._rels:
        rel_obj = doc.part._rels[rel]
        if "image" in rel_obj.target_ref:
            img_bytes = rel_obj.target_part.blob
            ext = Path(rel_obj.target_ref).suffix.lstrip(".")
            img_path = save_image(img_bytes, ext)
            # 这里简单放到最后一题（可根据需求插入位置）
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
