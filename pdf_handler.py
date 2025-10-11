import fitz  # pip install PyMuPDF
import os
import re
import uuid

# ===============================
# 配置
# ===============================
pdf_path = "2222.pdf"  # 你的 PDF 文件
output_dir = "pdf_md_parts"
os.makedirs(output_dir, exist_ok=True)

img_dir = os.path.join(output_dir, "images")
os.makedirs(img_dir, exist_ok=True)

# ===============================
# 1️⃣ 打开 PDF 并提取文本 + 图片
# ===============================
pages_content = []
pos_counter = 0

doc = fitz.open(pdf_path)

for page_index in range(len(doc)):
    page = doc[page_index]
    page_text = page.get_text()  # 获取页面文本
    page_images = []

    image_list = page.get_images(full=True)
    for img in image_list:
        xref = img[0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        ext = base_image["ext"]  # jpg/png 等
        img_name = f"{uuid.uuid4().hex}.{ext}"
        img_path = os.path.join(img_dir, img_name)
        with open(img_path, "wb") as f:
            f.write(image_bytes)
        page_images.append(os.path.join("images", img_name))

    pages_content.append({
        'start': pos_counter,
        'end': pos_counter + len(page_text),
        'text': page_text,
        'images': page_images
    })
    pos_counter += len(page_text) + 1

# ===============================
# 2️⃣ 按题号切分文本
# ===============================
question_pattern = r'(?m)^\s*(\d+)[．.\)]'  # 支持 1. 1． (1) 1)
all_text = "".join([p['text'] for p in pages_content])
matches = list(re.finditer(question_pattern, all_text))

parts = []
for idx, match in enumerate(matches):
    start = match.end()
    end = matches[idx + 1].start() if idx + 1 < len(matches) else len(all_text)
    part_text = all_text[start:end].strip()
    parts.append({'title': match.group(), 'text': part_text, 'start': start, 'end': end})

# ===============================
# 3️⃣ 将题目和对应图片匹配并写入 Markdown
# ===============================
for i, part in enumerate(parts, 1):
    part_text = part['text']
    part_start = part['start']
    part_end = part['end']

    # 匹配题目跨页的图片
    part_images = []
    for page in pages_content:
        if not (part_end < page['start'] or part_start > page['end']):
            part_images.extend(page['images'])

    # 插入图片 Markdown
    for img_path in part_images:
        part_text += f"\n\n![image]({img_path})\n"

    # 保存 Markdown
    filename = os.path.join(output_dir, f"pdf_part_{i}.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(part_text)

print(f"✅ PDF 按题目切分 + Markdown + 原始图片完成！输出目录: {output_dir}")
