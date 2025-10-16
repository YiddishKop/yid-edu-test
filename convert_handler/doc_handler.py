import os
import uuid
import re
import sys
import shutil
import subprocess
from pathlib import Path
from wand.image import Image as WandImage # 导入 Wand 库,注意wand库还要下载 imagemagick

# =========================
# 配置输入和输出
# =========================
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 项目根目录（convert_handler 的上一级）
INPUT_DOCX = None  # 将在 __main__ 中从命令行参数解析
# Pandoc 工作目录（用于 --extract-media 和临时 md），在 __main__ 中设置为 .pandoc_<docname>
OUTPUT_FOLDER = None
IMAGES_SUBFOLDER = "images"
PANDOC_MEDIA_FOLDER = "media"
# 其他在 __main__ 中设置的全局：
DOC_BASE_NAME = None            # 不含扩展名的 docx 名称
PARTS_OUTPUT_DIR = None         # 小 md 输出目录（项目根目录）
IMAGES_FINAL_DIR = None         # 根目录 images/<docname>/


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
    # 将大 Markdown 文本按指定正则进行切分，并保留每段匹配到的“标签文本”用于命名
    parts = []  # [(label, text)]
    current_text = ""
    current_label = None
    # 捕获组 1 专门捕获匹配到的标签内容，便于用于文件命名
    pattern = re.compile(
        r"(?m)^\s*(?:>\s*)*"                    # 行首 + 可选的 Markdown 引用前缀 '> '
        r"("                                      # 捕获开始：仅捕获标签本体用于命名
        r"(?:"                                   # 非捕获组：枚举可匹配的标签样式
        r"\d+[．.]|\d+[)]|"                     # 1. / 1) / 1． 等
        r"【例\d+】|【练习\d+】|【变式\d*-*\d*】|" # 【例1】/【练习1】/【变式1-1】 等
        r"例\d+|练习\d+|变式\d+|"               # 例1 / 练习1 / 变式1 等（无方括号）
        r"【答案】|【解析】|【详解】|【参考答案】|"   # 常见答案/解析标签（带括号）
        r"答案[:：]?|解析[:：]?|详解[:：]?|参考答案[:：]?" # 常见答案/解析标签（不带括号，允许中文/英文冒号）
        r")"                                      # 非捕获组结束
        r")\s*"                                 # 捕获结束及可选空白
    )

    def flush_current():
        nonlocal current_text, current_label
        if current_text.strip():
            parts.append((current_label, current_text.strip()))
        current_text = ""
        current_label = None

    for line in md_content.splitlines():
        m = pattern.match(line)
        if m:
            # 开启新段前，先把已有段落写入
            flush_current()
            current_label = m.group(1).strip()
            current_text += line + "\n"
        else:
            current_text += line + "\n"
    flush_current()
    return parts

def save_parts_to_md(parts):
    # parts: List[Tuple[label, text]]
    def sanitize_label(label):
        if not label:
            return ""
        # 去除 Windows 非法字符 < > : " / \ | ? *
        sanitized = re.sub(r'[<>:"/\\|?*]', '', label)
        # 压缩首尾空白
        sanitized = sanitized.strip()
        # 若是纯数字+标点的序号，如 '1．'、'2.'、'3)'，归一化为纯数字
        m_num = re.fullmatch(r"(\d+)[\s．.。)）]*", sanitized)
        if m_num:
            sanitized = m_num.group(1)
        # 将空白替换为下划线（尽量保持中文括号等特殊字符）
        sanitized = re.sub(r"\s+", "_", sanitized)
        return sanitized

    saved_files = []
    for i, (label, part) in enumerate(parts, 1):
        label_fragment = sanitize_label(label)
        if label_fragment:
            md_filename = PARTS_OUTPUT_DIR / f"word_part_{DOC_BASE_NAME}_{i}_{label_fragment}.md"
        else:
            md_filename = PARTS_OUTPUT_DIR / f"word_part_{DOC_BASE_NAME}_{i}.md"
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
    final_image_dir = IMAGES_FINAL_DIR
    
    # 步骤 1: 重命名或合并文件夹
    if pandoc_image_dir.exists():
        final_image_dir.mkdir(parents=True, exist_ok=True)
        if final_image_dir.exists() and final_image_dir != pandoc_image_dir:
            for item in pandoc_image_dir.iterdir():
                if item.is_file():
                    target = final_image_dir / item.name
                    if target.exists():
                        stem, suf = item.stem, item.suffix
                        k = 1
                        while True:
                            candidate = final_image_dir / f"{stem}_{k}{suf}"
                            if not candidate.exists():
                                target = candidate
                                break
                            k += 1
                    item.rename(target)
            try:
                pandoc_image_dir.rmdir()
            except OSError:
                pass
        else:
            pandoc_image_dir.rename(final_image_dir)
        print(f"图片目录已准备就绪: '{final_image_dir}'")
    else:
        print("未找到 Pandoc 提取的图片目录，跳过后续处理。")
        return

    # 步骤 2 & 3: 转换格式并重命名（WMF/EMF -> 同名 PNG；其它保留原名）
    rename_map = {}
    print("开始处理图片：转换格式并重命名...")
    for old_image_path in list(final_image_dir.iterdir()): # 使用 list() 复制，以防迭代时删除文件出错
        if not old_image_path.is_file():
            continue

        original_name = old_image_path.name
        
        # --- 新增：检查文件格式并转换 ---
        if old_image_path.suffix.lower() in ['.wmf', '.emf']:
            # 对于 WMF/EMF，转换为与原始文件同名的 PNG，便于后续路径替换
            new_name = f"{old_image_path.stem}.png"
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
        else: # 对于其他图片格式，保持原始文件名（不做重命名）
            new_name = original_name
            rename_map[original_name] = new_name

    if not rename_map:
        return

    # 步骤 4: 更新 Markdown 文件中的引用
    print("开始更新 Markdown 文件中的图片引用...")
    for md_file_path in md_files:
        with open(md_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # 基础路径修正：将任何指向 media/ 的引用改到 images/<docname>/
        correct_path_prefix = f"{IMAGES_SUBFOLDER}/{DOC_BASE_NAME}/"
        # 1) 包含工作目录名的前缀情况
        if OUTPUT_FOLDER is not None:
            path_prefix_to_remove = f"{OUTPUT_FOLDER.name}/{PANDOC_MEDIA_FOLDER}/"
            content = content.replace(path_prefix_to_remove, correct_path_prefix)
        # 2) 直接以 media/ 开头的相对路径
        content = re.sub(r"\((?:\./)?media/", f"({correct_path_prefix}", content)
        # 3) Windows 绝对路径中的 \\media\\
        content = re.sub(r"\((?:[A-Za-z]:)?[^)]*?\\media\\", f"({correct_path_prefix}", content)

        # 使用正则仅替换 Markdown 链接/图片目标中的文件名
        # 匹配模式：![alt](<path>) 或 [text](<path>)，path 可含空格、相对或绝对路径，支持 Windows 反斜杠
        link_pat = re.compile(r"(!?\[[^\]]*\]\()\s*<?([^)>]+?)>?\s*(\))")

        def replace_target_with_map(text, old_name, new_name):
            def _repl(m):
                before, target, after = m.group(1), m.group(2), m.group(3)
                norm = target.replace('\\\\', '/').replace('\\\\', '/')
                norm = norm.replace('\\', '/')
                base = norm.split('/')[-1]
                if base == old_name:
                    return f"{before}{correct_path_prefix}{new_name}{after}"
                return m.group(0)
            return link_pat.sub(_repl, text)

        for old_name, new_name in rename_map.items():
            content = replace_target_with_map(content, old_name, new_name)

        # 移除 Pandoc/kramdown 风格的行内属性块：如 {width="2in" height="1in"}
        # 形式通常紧跟在链接/图片之后：![alt](path){...}
        # 将 {...} 整段删除，保留前面的链接/图片本体
        content = re.sub(r"(!?\[[^\]]*\]\([^\)]*\))\s*\{[^}]*\}", r"\1", content)

        if content != original_content:
            with open(md_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"已更新文件: {md_file_path}")


# =========================
# 执行
# =========================
if __name__ == "__main__":
    # 1) 解析命令行参数：python doc_handler.py <docx_path>
    if len(sys.argv) < 2:
        print("用法: python doc_handler.py <docx文件路径>")
        sys.exit(1)

    INPUT_DOCX = Path(sys.argv[1])
    if not INPUT_DOCX.exists():
        print(f"错误：未找到文件: {INPUT_DOCX}")
        sys.exit(1)

    # 2) 设置输出结构：
    #    - 小 md：项目根目录
    #    - 图片：images/<docname>/
    #    - Pandoc 工作目录：.pandoc_<docname>
    DOC_BASE_NAME = INPUT_DOCX.stem
    PARTS_OUTPUT_DIR = PROJECT_ROOT
    IMAGES_FINAL_DIR = PROJECT_ROOT / IMAGES_SUBFOLDER / DOC_BASE_NAME
    OUTPUT_FOLDER = PROJECT_ROOT / f".pandoc_{DOC_BASE_NAME}"
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    IMAGES_FINAL_DIR.mkdir(parents=True, exist_ok=True)

    # 3) 执行转换与分割
    md_content, temp_file = pandoc_convert_and_parse(INPUT_DOCX)

    if md_content:
        md_parts = parse_md(md_content)
        saved_md_files = save_parts_to_md(md_parts)
        process_images_and_update_references(saved_md_files)

        # 4) 清理临时文件与工作目录
        if temp_file and temp_file.exists():
            try:
                os.remove(temp_file)
                print(f"已清理临时文件: {temp_file.name}")
            except OSError:
                pass
        try:
            shutil.rmtree(OUTPUT_FOLDER)
            print(f"已清理工作目录: {OUTPUT_FOLDER}")
        except Exception:
            pass
