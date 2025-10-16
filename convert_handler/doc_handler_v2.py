import os
import io
import uuid
import re
import docx
from lxml import etree

WORD_FOLDER = r"."
OUTPUT_FOLDER = r"word_md_parts"
IMAGES_SUBFOLDER = "images"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_FOLDER, IMAGES_SUBFOLDER), exist_ok=True)

# 题号正则
QUESTION_RE = re.compile(
    r'(?m)^\s*(?:'
    r'\d+[\.\．\)\、]'  # 数字 + 标点
    r'|例\s*\d+'       # 例1 / 例 1
    r'|练习\s*\d+'     # 练习1 / 练习 1
    r')'
)

def omml_to_latex(run):
    """
    将 Word 中 OMML 公式转换为 LaTeX 占位符
    run: docx run 对象
    """
    elem = run._element
    ns = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
    omml_elements = elem.findall('.//m:oMath', ns)
    if not omml_elements:
        return ""
    latex_parts = []
    for omml in omml_elements:
        try:
            xml_str = etree.tostring(omml, encoding="unicode")
            latex_parts.append(f"$$ {xml_str} $$")
        except Exception:
            latex_parts.append("$$公式转换失败$$")
    return "\n".join(latex_parts)

def parse_docx_with_images_and_formula(file_path):
    doc = docx.Document(file_path)
    result = []

    # 收集图片
    image_map = {}
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            img_data = rel.target_part.blob
            ext = rel.target_part.content_type.split("/")[-1]
            img_name = f"{uuid.uuid4().hex}.{ext}"
            img_path = os.path.join(OUTPUT_FOLDER, IMAGES_SUBFOLDER, img_name)
            with open(img_path, "wb") as f:
                f.write(img_data)
            image_map[rel.rId] = img_name

    for p in doc.paragraphs:
        paragraph_text = ""
        for run in p.runs:
            # 文本
            if run.text:
                paragraph_text += run.text
            # 图片
            pics = run._element.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/picture}pic')
            for pic in pics:
                blips = pic.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
                for blip in blips:
                    rId = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                    if rId and rId in image_map:
                        img_name = image_map[rId]
                        paragraph_text += f"\n\n![{img_name}]({IMAGES_SUBFOLDER}/{img_name})\n\n"
            # 公式
            latex_formula = omml_to_latex(run)
            if latex_formula:
                paragraph_text += f"\n{latex_formula}\n"
        if paragraph_text.strip():
            result.append(paragraph_text.strip())

    full_text = "\n\n".join(result)
    return full_text

# 遍历 Word 文件夹
for fname in os.listdir(WORD_FOLDER):
    if not fname.lower().endswith(".docx"):
        continue

    file_path = os.path.join(WORD_FOLDER, fname)
    text = parse_docx_with_images_and_formula(file_path)

    # 按题号切分
    parts = re.split(QUESTION_RE, text)
    parts = [p.strip() for p in parts if p.strip()]

    for i, part in enumerate(parts, 1):
        md_filename = f"word_part_{i}.md"
        md_path = os.path.join(OUTPUT_FOLDER, md_filename)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(part)

    print(f"处理完成 {fname}，生成 {len(parts)} 个 md 文件")
