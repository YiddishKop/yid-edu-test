import os
import uuid
import re
import subprocess
from pathlib import Path
from wand.image import Image as WandImage # 导入 Wand 库

# =========================
# 配置输入和输出
# =========================
INPUT_DOCX = "2222.docx"
OUTPUT_FOLDER = Path("word_md_parts")
IMAGES_SUBFOLDER = "images"
PANDOC_MEDIA_FOLDER = "media"

# 确保输出目录存在
(OUTPUT_FOLDER / IMAGES_SUBFOLDER).mkdir(parents=True, exist_ok=True)

# =========================
# Pandoc 转换函数 (不变)
# =========================
def pandoc_convert_and_parse(docx_path):
    print(f"正在使用 Pandoc 转换文件：{docx_path}...")
    temp_md_file = OUTPUT_FOLDER / "temp_pandoc_output.md"
    
    pandoc_command = [
        "pandoc", str(docx_path), "-o", str(temp_md_file),
        "-t", "markdown-raw_tex", f"--extract-media={str(OUTPUT_FOLDER)}"
    ]

    try:
        subprocess.run(
            pandoc_command, check=True, capture_output=True, text=True, encoding="utf-8"
        )
        print("Pandoc 转换成功。")
        with open(temp_md_file, "r", encoding="utf-8") as f:
            md_content = f.read()
        pandoc_image_dir = OUTPUT_FOLDER / PANDOC_MEDIA_FOLDER
        if pandoc_image_dir.exists():
            print(f"Pandoc 已将图片提取到: {pandoc_image_dir}")
        else:
            print("警告：Pandoc 未能提取任何图片。")
        return md_content, temp_md_file
    except FileNotFoundError:
        print("错误：未找到 'pandoc' 命令。请确保 Pandoc 已安装并配置到系统 PATH 中。")
        return None, None
    except subprocess.CalledProcessError as e:
        print(f"错误：Pandoc 转换失败，错误信息如下：\n{e.stderr}")
        return None, None
    except Exception as e:
        print(f"发生未知错误: {e}")
        return None, None

# =========================
# 内容解析与保存函数 (不变)
# =========================
def parse_md(md_content):
    # ... (代码与之前版本相同，此处省略)
    parts = []
    current_text = ""
    pattern = re.compile(
        r'(?m)^\s*'
        r'(?:'
        r'\d+[．.]|\d+[)]|'         
        r'【例\d+】|【练习\d+】|【变式\d*-*\d*】|' 
        r'例\d+|练习\d+|变式\d+|'
        r'【答案】|【解析】|【参考答案】'     
        r')\s*'
    )
    def flush_current():
        nonlocal current_text
        if current_text.strip():
            parts.append(current_text.strip())
        current_text = ""
        
    for line in md_content.splitlines():
        if pattern.match(line):
            flush_current()
            current_text += line + "\n"
        else:
            current_text += line + "\n"
    flush_current()
    return parts

def save_parts_to_md(parts):
    # ... (代码与之前版本相同，此处省略)
    saved_files = []
    for i, part in enumerate(parts, 1):
        md_filename = OUTPUT_FOLDER / f"word_part_{i}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(part)
        saved_files.append(str(md_filename))
    print(f"成功将内容分割为 {len(parts)} 个 Markdown 文件。")
    return saved_files

# =========================
# ✅ 最终修正：集成 WMF 转换、UUID 重命名并修正路径
# =========================
def process_images_and_update_references(md_files):
    """
    1. 将 'media' 文件夹重命名为 'images'。
    2. 遍历 'images' 文件夹，将 WMF/EMF 文件转换为 PNG。
    3. 为所有图片生成 UUID 文件名。
    4. 修正并更新所有 Markdown 文件中的引用路径。
    """
    pandoc_image_dir = OUTPUT_FOLDER / PANDOC_MEDIA_FOLDER
    final_image_dir = OUTPUT_FOLDER / IMAGES_SUBFOLDER
    
    # 步骤 1: 重命名或合并文件夹
    if pandoc_image_dir.exists():
        if final_image_dir.exists() and final_image_dir != pandoc_image_dir:
            for item in pandoc_image_dir.iterdir():
                item.rename(final_image_dir / item.name)
            pandoc_image_dir.rmdir()
        else:
            pandoc_image_dir.rename(final_image_dir)
        print(f"图片目录已准备就绪: '{final_image_dir}'")
    else:
        print("未找到 Pandoc 提取的图片目录，跳过后续处理。")
        return

    # 步骤 2 & 3: 转换格式并用 UUID 重命名
    rename_map = {}
    print("开始处理图片：转换格式并重命名...")
    for old_image_path in list(final_image_dir.iterdir()): # 使用 list() 复制，以防迭代时删除文件出错
        if not old_image_path.is_file():
            continue

        original_name = old_image_path.name
        
        # --- 新增：检查文件格式并转换 ---
        if old_image_path.suffix.lower() in ['.wmf', '.emf']:
            new_name = f"{uuid.uuid4().hex}.png"
            new_image_path = final_image_dir / new_name
            try:
                with WandImage(filename=str(old_image_path)) as img:
                    img.format = 'png'
                    img.save(filename=str(new_image_path))
                os.remove(old_image_path) # 删除原始的 wmf/emf 文件
                rename_map[original_name] = new_name
                print(f"转换并重命名: {original_name} -> {new_name}")
            except Exception as e:
                print(f"错误：转换文件 {original_name} 失败: {e}")
        else: # 对于其他图片格式，直接重命名
            new_name = f"{uuid.uuid4().hex}{old_image_path.suffix}"
            new_image_path = final_image_dir / new_name
            old_image_path.rename(new_image_path)
            rename_map[original_name] = new_name
            print(f"重命名: {original_name} -> {new_name}")

    if not rename_map:
        return

    # 步骤 4: 更新 Markdown 文件中的引用
    print("开始更新 Markdown 文件中的图片引用...")
    for md_file_path in md_files:
        with open(md_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # 修正路径前缀
        path_prefix_to_remove = f"{OUTPUT_FOLDER.name}/{PANDOC_MEDIA_FOLDER}/"
        correct_path_prefix = f"{IMAGES_SUBFOLDER}/"
        content = content.replace(path_prefix_to_remove, correct_path_prefix)
        path_prefix_to_remove_alt = f"{OUTPUT_FOLDER.name}/{IMAGES_SUBFOLDER}/"
        content = content.replace(path_prefix_to_remove_alt, correct_path_prefix)

        # 更新为新的 UUID 文件名
        for old_name, new_name in rename_map.items():
            content = content.replace(f"({IMAGES_SUBFOLDER}/{old_name})", f"({IMAGES_SUBFOLDER}/{new_name})")
        
        if content != original_content:
            with open(md_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"已更新文件: {md_file_path}")


# =========================
# 执行
# =========================
if __name__ == "__main__":
    md_content, temp_file = pandoc_convert_and_parse(INPUT_DOCX)
    
    if md_content:
        md_parts = parse_md(md_content)
        saved_md_files = save_parts_to_md(md_parts)
        process_images_and_update_references(saved_md_files) # 调用最终修正的函数

        if temp_file and temp_file.exists():
            os.remove(temp_file)
            print(f"已清理临时文件: {temp_file.name}")