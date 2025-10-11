import os
import re
import uuid
import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT

def word_to_md_split_v2(doc_path, output_root="word_md_parts"):
    output_dir = output_root
    image_dir = os.path.join(output_root, "images")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(image_dir, exist_ok=True)

    doc = docx.Document(doc_path)
    full_text = []
    image_map = {}
    current_question = None

    # 1) 提取文本并识别题号
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        m = re.match(r'^(\d+)[\.\、\)]', text)
        if m:
            current_question = int(m.group(1))
        if current_question:
            full_text.append((current_question, text))

    # 2) 提取图片，归属最近题目，使用 UUID 命名
    for rel in doc.part.rels.values():
        if rel.reltype == RT.IMAGE:
            img_data = rel.target_part.blob
            img_ext = os.path.splitext(rel.target_part.partname)[1] or ".png"
            img_name = f"{uuid.uuid4().hex}{img_ext}"
            img_path = os.path.join(image_dir, img_name)
            with open(img_path, "wb") as f:
                f.write(img_data)
            if current_question:
                image_map.setdefault(current_question, []).append(img_name)

    # 3) 根据题号分组
    questions = {}
    for qnum, text in full_text:
        questions.setdefault(qnum, []).append(text)

    # 4) 写入 md
    for qnum, contents in questions.items():
        md_lines = []
        for line in contents:
            line = line.replace("_____", "\\underline{~~~~}")
            md_lines.append(line)

        if qnum in image_map:
            for img_name in image_map[qnum]:
                img_rel_path = f"images/{img_name}"
                md_lines.append(f"![{img_name}]({img_rel_path})")

        filename = os.path.join(output_dir, f"word_part_{qnum}.md")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n\n".join(md_lines))

        print(f"✅ 已生成：{filename}")

    print("✅ 全部完成！输出目录：", output_dir)


if __name__ == "__main__":
    word_to_md_split_v2("1111.docx")
