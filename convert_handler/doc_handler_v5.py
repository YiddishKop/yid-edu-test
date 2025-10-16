import os
import uuid
import re
import subprocess
from pathlib import Path
# 移除了 from docx import Document 等 python-docx 依赖
# 移除了 from docx.oxml.ns import qn 等 xml 解析工具
from PIL import Image
from wand.image import Image as WandImage

# =========================
# 配置输入和输出
# =========================
INPUT_DOCX = "2222.docx"  # 要处理的 Word 文件
OUTPUT_FOLDER = "word_md_parts"
IMAGES_SUBFOLDER = "images"
TEMP_MD_FILE = Path(OUTPUT_FOLDER, "temp_pandoc_output.md")

# 确保输出目录存在
Path(OUTPUT_FOLDER, IMAGES_SUBFOLDER).mkdir(parents=True, exist_ok=True)

# =========================
# ✅ 移除：不再需要 Word 下划线和 Run 逻辑
# =========================
# 由于 Pandoc 已经将 Word 转换为 Markdown，我们不需要手动处理 runs 和下划线了。

# =========================
# 保持不变：工具函数：保存图片 (兼容 Word 内部的 EMF/WMF 格式)
# ----------------------------------------------------------------------
# 注意：在当前 Pandoc 流程中，Pandoc 直接保存图片，此函数可能不再执行
# 但保留其定义以防 Pandoc 无法处理特定格式时使用。
# ----------------------------------------------------------------------
def save_image(image_bytes, ext):
    """
    保存图片字节流，并处理 EMF/WMF 格式转换为 PNG。
    (图片文件名已使用 UUID 保证唯一性)
    """
    img_uuid = f"{uuid.uuid4().hex}.png"
    out_path = os.path.join(OUTPUT_FOLDER, IMAGES_SUBFOLDER, img_uuid)

    if ext.lower() in ["emf", "wmf"]:
        with WandImage(blob=image_bytes) as img:
            img.format = "png"
            img.save(filename=out_path)
    else:
        with open(out_path, "wb") as f:
            f.write(image_bytes)

    # 返回相对路径，例如 "images/uuid.png"，供可能的手动插入使用
    return os.path.join(IMAGES_SUBFOLDER, img_uuid)


# =========================
# ✅ 核心新增：使用 Pandoc 转换 Word (修正路径)
# =========================
def pandoc_convert_and_parse(docx_path):
    """
    使用 Pandoc 将 Word 转换为 Markdown，并将公式转换为 LaTeX。
    将图片提取路径设置为相对路径。
    """
    print(f"正在使用 Pandoc 转换文件：{docx_path}...")
    
    # --- 修正点 1: 确保 --extract-media 参数是相对路径 ---
    # 我们希望图片路径相对于最终的 Markdown 文件 (temp_pandoc_output.md)，
    # 即使用 IMAGES_SUBFOLDER (e.g., "images") 作为路径。
    # 
    # 如果 pandoc 命令在项目的根目录运行，且输出文件在 word_md_parts/temp_pandoc_output.md
    # 则 --extract-media 的路径应该相对于 word_md_parts 文件夹。
    
    # 解决方案：使用相对路径 'images'
    relative_media_path = IMAGES_SUBFOLDER 

    pandoc_command = [
        "pandoc",
        "-s",
        str(docx_path),
        "-o",
        str(TEMP_MD_FILE),
        "-t",
        "markdown-raw_tex",
        f"--extract-media={relative_media_path}"
    ]
    # ---------------------------------------------------------

    try:
        # 执行命令
        # 注意：这里假设 os.getcwd() 是项目根目录，Path(OUTPUT_FOLDER) 位于其下
        # 否则需要调整 pandoc_command 中的路径
        result = subprocess.run(
            pandoc_command, 
            check=True, 
            capture_output=True, 
            text=True, 
            encoding="utf-8"
        )
        print("Pandoc 转换成功。")

        # 转换成功后，读取生成的临时 Markdown 文件并进行分割
        with open(TEMP_MD_FILE, "r", encoding="utf-8") as f:
            md_content = f.read()

        return parse_md(md_content)

    except FileNotFoundError:
        print("错误：未找到 'pandoc' 命令。请确保 Pandoc 已安装并配置到系统 PATH 中。")
        return []
    except subprocess.CalledProcessError as e:
        print(f"错误：Pandoc 转换失败，错误信息如下：\n{e.stderr}")
        return []
    except Exception as e:
        print(f"发生未知错误: {e}")
        return []

# =========================
# ✅ 修改：parse_md (解析 Markdown 内容)
# =========================
def parse_md(md_content):
    """
    分割 Pandoc 转换后的 Markdown 内容。
    
    修正点 2: Pandoc 默认以 'media/' 命名图片文件夹，需要替换为 'images/'
    """
    # ----------------------------------------------------------------------
    # 修正点 2: 替换 Pandoc 默认的图片路径 'media/' 为我们定义的 'images/'
    # Pandoc 在 --extract-media 时，文件名会使用 Word 内部的 rID 或名字，
    # 但路径会是 --extract-media 指定的值。
    # 如果你发现生成的 Markdown 链接路径不对，可以在此进行替换：
    # 例如：![](media/image1.png) -> ![](images/image1.png)
    
    # 由于我们设置了 --extract-media=images，这里的替换可能不是必须的，
    # 但作为后处理的健壮性考虑，如果你发现路径不对，可以开启以下代码：
    # md_content = md_content.replace(f"({os.path.basename(IMAGES_SUBFOLDER)}/", f"({IMAGES_SUBFOLDER}/")
    # ----------------------------------------------------------------------
    
    parts = []
    current_text = ""
    
    # 正则表达式保持不变
    pattern = re.compile(
        r'(?m)^\s*'
        r'(?:'
        r'\d+[．.]|\d+[)]|'         
        r'【例\d+】|【练习\d+】|【变式\d*-*\d*】|' 
        r'例\d+|练习\d+|变式\d+'     
        r')\s*'
    )

    def flush_current():
        nonlocal current_text
        if current_text.strip():
            parts.append(current_text.strip())
        current_text = ""
    
    # 按行处理内容
    for line in md_content.splitlines():
        
        # 匹配分割点
        if pattern.match(line):
            flush_current()
            current_text += line + "\n"
        else:
            current_text += line + "\n"

    flush_current()
    
    return parts

# =========================
# 主流程：生成 Markdown 文件
# =========================
def save_parts_to_md(parts):
    for i, part in enumerate(parts, 1):
        md_filename = os.path.join(OUTPUT_FOLDER, f"word_part_{i}.md")
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(part)
    print(f"成功将内容分割为 {len(parts)} 个 Markdown 文件到 {OUTPUT_FOLDER} 文件夹。")
    
    # 清理临时文件
    if TEMP_MD_FILE.exists():
        os.remove(TEMP_MD_FILE)
        print(f"已清理临时文件: {TEMP_MD_FILE.name}")


# =========================
# 执行
# =========================
if __name__ == "__main__":
    # 执行 Pandoc 转换和内容解析
    md_parts = pandoc_convert_and_parse(INPUT_DOCX)
    
    # 只有在解析出内容时才保存
    if md_parts:
        save_parts_to_md(md_parts)