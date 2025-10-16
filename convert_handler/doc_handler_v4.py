import os
import uuid
import re
from pathlib import Path
from docx import Document
from PIL import Image
from wand.image import Image as WandImage
# 引入 docx 内部的 XML 命名空间工具，用于准确提取图片 ID
from docx.oxml.ns import qn

# =========================
# 配置输出目录
# =========================
INPUT_DOCX = "2222.docx"  # 要处理的 Word 文件
OUTPUT_FOLDER = "word_md_parts"
IMAGES_SUBFOLDER = "images"

Path(OUTPUT_FOLDER, IMAGES_SUBFOLDER).mkdir(parents=True, exist_ok=True)

# =========================
# ✅ 保持不变：提取含下划线 run 的文本
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

    return "".join(parts) # 移除 .strip()

# =========================
# 保持不变：工具函数：保存图片
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
# ✅ 核心修改：按段落位置插入图片
# =========================
def parse_docx(docx_path):
    doc = Document(docx_path)
    parts = []

    current_text = ""
    
    # 修正后的正则表达式，支持 【例1】 格式
    pattern = re.compile(
        r'(?m)^\s*'
        r'(?:'
        r'\d+[．.]|\d+[)]|'         # 匹配 1. 或 1)
        r'【例\d+】|【练习\d+】|【变式\d*-*\d*】|' # 2. 【例1】 这种带方括号的格式
        r'例\d+|练习\d+|变式\d+'     # 匹配 例1, 练习1 等
        r')\s*'
    )

    def flush_current():
        nonlocal current_text
        if current_text.strip():
            parts.append(current_text.strip())
        current_text = ""

    # 新增：记录已处理的图片 rId，避免重复保存
    processed_rids = set()

    for para in doc.paragraphs:
        
        # 1. 提取段落文本 (包含下划线处理)
        text = extract_text_with_underline(para)
        
        # 2. 检查段落中的内嵌图片 (Inline Shapes) 并插入 Markdown
        image_markdown = ""
        
        # 遍历段落中的所有 runs，因为图片总是嵌入在某个 run 中
        for run in para.runs:
            # 尝试在 run 的 XML 元素中查找 drawing 元素
            drawing_elements = run._element.xpath('.//w:drawing')
            
            if drawing_elements:
                # 尝试从 drawing 元素中提取 rId，这是定位内嵌图片的标准方法
                # 使用 qn 确保命名空间正确
                # blip_elements = run._element.xpath('.//a:blip', namespaces=run._element.nsmap)
                from docx.oxml.ns import qn, nsdecls # 确保 nsdecls 已导入

                # 修正后的行：使用 qn 查找带命名空间前缀的元素
                # 注意：这里可能需要依赖 run.element 已经处理了命名空间。
                # 更好的方法是使用 lxml 的原始 XPath 方式，但为了兼容性，我们尝试简化。
                # 如果直接查找失败，我们需要采用另一种 XPath 语法。

                # 尝试直接使用通配符查找，这在某些环境中有效，但会降低准确性
                blip_elements = run._element.xpath('.//*[local-name()="blip"]')

                # 或者，如果 docx 的 qn 导入能工作，尝试使用 qn
                # blip_elements = run._element.xpath(f'.//{qn("a:blip")}') 
                # 但这可能会报同样的错误，因为我们仍然在直接使用 BaseOxmlElement.xpath。
                
                if blip_elements:
                    blip = blip_elements[0]
                    # 获取 r:embed 属性的值，即图片的关系 ID
                    rId = blip.get(qn('r:embed'))
                    
                    if rId and rId not in processed_rids:
                        
                        # 1. 保存图片
                        rel_obj = doc.part.rels[rId]
                        img_bytes = rel_obj.target_part.blob
                        ext = Path(rel_obj.target_ref).suffix.lstrip(".")
                        img_path = save_image(img_bytes, ext)
                        
                        # 2. 将 Markdown 链接添加到图片 run 的位置
                        image_markdown += f"![image]({img_path})"
                        processed_rids.add(rId) # 标记为已处理
        
        # 3. 组合完整的段落内容 (文本 + 附加的图片 Markdown)
        full_para_content = text.strip()
        
        # 将图片 Markdown 附加到段落文本后，实现段落级定位
        full_para_content += image_markdown
        
        if not full_para_content.strip():
            continue

        # 4. 应用分割逻辑
        if pattern.match(full_para_content):
            flush_current()
            current_text += full_para_content + "\n"
        else:
            current_text += full_para_content + "\n"

    flush_current()

    # 移除原先的 final image loop (它不再被需要)

    return parts

# =========================
# 主流程：生成 Markdown 文件 (保持不变)
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