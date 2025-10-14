# streamlit_run_modified.py
import streamlit as st
import json
import io
import os
import tempfile
import subprocess
import traceback
from pathlib import Path
import re
import base64

from sqlalchemy import (
    create_engine, Column, Integer, Text, String,
    TIMESTAMP, ARRAY, func, and_, or_, SmallInteger
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# optional libs
try:
    import docx
except Exception:
    docx = None
try:
    import pdfplumber
except Exception:
    pdfplumber = None
try:
    import pypandoc
except Exception:
    pypandoc = None

import math
import html
import streamlit.components.v1 as components

# ===============================
# Config
# ===============================
DB_USER = "yiddi"
DB_PASSWORD = "020297"
DB_NAME = "exam_db"
DB_HOST = "localhost"
DB_PORT = "5432"
XELATEX_CMD = "xelatex"
DVISVGM_CMD = "dvisvgm"
WORD_PARTS_FOLDER = "word_md_parts"
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
AUTH_USERS = {"admin": "admin123"}

# ===============================
# DB init & ORM
# ===============================
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text)
    content_md = Column(Text)
    content_latex = Column(Text)
    course_id = Column(Integer)
    grade_id = Column(Integer)
    chapter_id = Column(Integer)
    knowledge_points = Column(ARRAY(Text))
    question_type = Column(String(50))
    difficulty = Column(Integer)
    answer = Column(Text)
    analysis = Column(Text)
    extra_metadata = Column("metadata", JSONB)
    quality = Column(SmallInteger)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

# ===============================
# Helpers
# ===============================
def render_markdown_with_images(md_text: str, base_path: str):
    if not md_text: return ""
    img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
    def replacer(match):
        alt_text, img_path_str = match.group(1), match.group(2)
        full_img_path = Path(base_path) / img_path_str
        if full_img_path.exists() and full_img_path.is_file():
            try:
                img_data = full_img_path.read_bytes()
                b64_data = base64.b64encode(img_data).decode('utf-8')
                ext = full_img_path.suffix.lower()
                mime_type = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.svg': 'image/svg+xml'}.get(ext, 'application/octet-stream')
                data_uri = f'data:{mime_type};base64,{b64_data}'
                return f'<img src="{data_uri}" alt="{alt_text}" style="max-width: 100%;">'
            except Exception as e: return f"![{alt_text}](图片加载失败: {e})"
        else: return f"![{alt_text}]({img_path_str} '图片未找到')"
    return img_pattern.sub(replacer, md_text)

def parse_docx_bytes(file_bytes):
    if docx is None: raise RuntimeError("python-docx 未安装")
    stream = io.BytesIO(file_bytes)
    document = docx.Document(stream)
    return "\n\n".join([p.text.strip() for p in document.paragraphs if p.text.strip()])

def parse_pdf_bytes(file_bytes):
    if pdfplumber is None: raise RuntimeError("pdfplumber 未安装")
    pdfplumber.pdf.PDFPage.images_backend = "mutool"
    stream = io.BytesIO(file_bytes)
    with pdfplumber.open(stream) as pdf:
        return "\n\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])

# ✅ [修改] 修正 md_to_latex 函数以移除 \pandocbounded
def md_to_latex(md_text):
    """
    使用 pypandoc 将 Markdown 转换为 LaTeX，并移除 pandoc 特定的 \pandocbounded 命令。
    """
    if not md_text: return ""
    if pypandoc is None: return f"% (Warning: pypandoc not installed) \n{md_text}"
    try:
        # 步骤 1: 正常使用 pypandoc 进行转换
        latex_output = pypandoc.convert_text(md_text, 'latex', format='md')
        
        # 步骤 2: 使用正则表达式移除 \pandocbounded{...} 包装器
        # re.DOTALL 标志确保可以处理跨行的内容
        cleaned_latex = re.sub(r'\\pandocbounded{(.*?)}', r'\1', latex_output, flags=re.DOTALL)
        
        return cleaned_latex
    except Exception as e:
        return f"% (pandoc convert failed: {e}) \n{md_text}"

# ===============================
# LaTeX -> SVG (xelatex + dvisvgm)
# ===============================
def latex_full_document_body(user_tex: str, image_base_path: Path):
    graphics_path_str = image_base_path.resolve().as_posix()
    preamble = rf"""
\documentclass[12pt]{{article}}
\usepackage{{amsmath,amssymb}}
\usepackage{{graphicx}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\setCJKmainfont{{SimSun}}

\graphicspath{{{{{graphics_path_str}/}}}}

\pagestyle{{empty}}
\parindent=0pt
\begin{{document}}
"""
    ending = r"""
\end{document}
"""
    return preamble + user_tex + ending

def compile_latex_to_svg(tex_body: str, timeout=20):
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        tex_file = td_path / "preview.tex"
        pdf_file = td_path / "preview.pdf"
        svg_file = td_path / "preview.svg"
        tex_file.write_text(tex_body, encoding="utf-8")

        try:
            proc = subprocess.run(
                [XELATEX_CMD, "-interaction=nonstopmode", "-halt-on-error", str(tex_file.name)],
                cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return False, f"XeLaTeX 超时（>{timeout}s）。"

        if not pdf_file.exists():
            stdout = proc.stdout.decode("utf-8", errors="ignore")
            stderr = proc.stderr.decode("utf-8", errors="ignore")
            logs = stdout + "\n" + stderr
            for path in td_path.glob("*.log"):
                try: logs += f"\n\n==== LOG: {path.name} ====\n" + path.read_text(encoding="utf-8", errors="ignore")
                except Exception: pass
            return False, f"XeLaTeX 编译失败：\n{logs}"

        try:
            proc2 = subprocess.run(
                [DVISVGM_CMD, "--pdf", str(pdf_file.name), "-n", "-o", str(svg_file.name)],
                cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False
            )
        except subprocess.TimeoutExpired:
            return False, "dvisvgm 超时。"

        if not svg_file.exists():
            out2 = proc2.stdout.decode("utf-8", errors="ignore")
            err2 = proc2.stderr.decode("utf-8", errors="ignore")
            return False, f"dvisvgm 转换失败：\n{out2}\n{err2}"

        return True, svg_file.read_text(encoding="utf-8", errors="ignore")

# ===============================
# Login widget
# ===============================
def login_widget():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if not st.session_state.logged_in:
        st.sidebar.title("🔒 登录")
        username = st.sidebar.text_input("用户名")
        password = st.sidebar.text_input("密码", type="password")
        if st.sidebar.button("登录"):
            if username in AUTH_USERS and AUTH_USERS[username] == password:
                st.session_state.logged_in = True
                st.session_state.user = username
                st.rerun()
            else: st.sidebar.error("用户名或密码错误")
        st.sidebar.info("示例账号：admin / admin123")
        return False
    else:
        st.sidebar.success(f"已登录：{st.session_state.user}")
        if st.sidebar.button("登出"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()
        return True

# ===============================
# App UI
# ===============================
st.set_page_config(page_title="题库管理（LaTeX 精确预览）", layout="wide")
st.title("题库管理（LaTeX 精确预览）")

if not login_widget():
    st.stop()

left_col, right_col = st.columns([3, 2])

with left_col:
    st.header("上传 & 编辑（Markdown / LaTeX）")
    uploaded = st.file_uploader("上传 .md / .txt / .docx / .pdf", type=["md", "txt", "docx", "pdf"])
    default_md = ""
    if uploaded is not None:
        raw = uploaded.read()
        name = uploaded.name.lower()
        try:
            if name.endswith(".docx"): default_md = parse_docx_bytes(raw)
            elif name.endswith(".pdf"): default_md = parse_pdf_bytes(raw)
            else: default_md = raw.decode("utf-8")
        except Exception as e:
            st.error(f"解析文件失败：{e}")

    st.subheader("1) Markdown 编辑与预览")
    if "markdown_buffer" not in st.session_state: st.session_state.markdown_buffer = default_md
    if uploaded is not None and st.button("以上传内容覆盖编辑区"): st.session_state.markdown_buffer = default_md
    md_text = st.text_area("Markdown 编辑", value=st.session_state.get("markdown_buffer",""), height=220)
    st.session_state.markdown_buffer = md_text
    st.markdown("**Markdown 预览：**")
    rendered_html_md = render_markdown_with_images(md_text, WORD_PARTS_FOLDER)
    st.markdown(rendered_html_md, unsafe_allow_html=True)

    st.markdown("---")
    auto_latex = md_to_latex(md_text)
    st.subheader("2) LaTeX 编辑（基于 Markdown 自动生成）")
    if "latex_buffer" not in st.session_state: st.session_state.latex_buffer = auto_latex
    if st.button("用自动生成的 LaTeX 覆盖编辑区"): st.session_state.latex_buffer = auto_latex
    latex_text = st.text_area("LaTeX 编辑", value=st.session_state.get("latex_buffer",""), height=260)
    st.session_state.latex_buffer = latex_text

    st.markdown("**3) 精确 LaTeX 预览（XeLaTeX + dvisvgm -> SVG）**")
    if st.button("生成精确预览 (编译 LaTeX)"):
        image_base_path = Path(WORD_PARTS_FOLDER)
        doc = latex_full_document_body(latex_text, image_base_path)
        success, result = compile_latex_to_svg(doc, timeout=25)
        st.session_state._latex_preview_success = success
        st.session_state._latex_preview_result = result
    
    if "_latex_preview_result" in st.session_state:
        if st.session_state._latex_preview_success:
            components.html(st.session_state._latex_preview_result, height=300, scrolling=True)
        else:
            st.error("LaTeX 编译或转换失败，以下为错误日志：")
            st.text(st.session_state._latex_preview_result[:10000])

    st.markdown("---")
    st.subheader("4) 结构化元信息（将写入字段）")
    title = st.text_input("题目标题或简述")
    col_ids_1, col_ids_2, col_ids_3 = st.columns(3)
    with col_ids_1: course_id = st.number_input("课程 ID", min_value=0, value=0, step=1)
    with col_ids_2: grade_id = st.number_input("年级 ID", min_value=0, value=0, step=1)
    with col_ids_3: chapter_id = st.number_input("章节 ID", min_value=0, value=0, step=1)
    q_type = st.text_input("题目类型（单选/多选/解答）")
    difficulty = st.number_input("难度（1-5）", 1, 5, 3)
    quality = st.number_input("题目质量 (1-5)", 1, 5, 3)
    answer = st.text_input("答案")
    analysis = st.text_area("解析")
    kp_raw = st.text_input("知识点（逗号分隔）")
    meta_raw = st.text_area("额外 metadata JSON（可选）", value="")

    if st.button("✅ 确认 LaTeX 并写入数据库"):
        if not st.session_state.get("_latex_preview_success", False):
            st.warning("请先点击“生成精确预览 (编译 LaTeX)”并确认渲染结果无误，再保存。")
        else:
            db = SessionLocal()
            try:
                extra_meta = {}
                if meta_raw.strip():
                    try: extra_meta = json.loads(meta_raw.replace("\\","/"))
                    except Exception: st.warning("额外 metadata 不是合法 JSON，已存空对象。")
                kp_list = [kp.strip() for kp in kp_raw.split(",")] if kp_raw.strip() else None
                q = Question(
                    title=title or None, content_md=md_text or None, content_latex=latex_text or None,
                    course_id=course_id if course_id > 0 else None,
                    grade_id=grade_id if grade_id > 0 else None,
                    chapter_id=chapter_id if chapter_id > 0 else None,
                    knowledge_points=kp_list, question_type=q_type or None,
                    difficulty=int(difficulty) if difficulty else None,
                    answer=answer or None, analysis=analysis or None,
                    extra_metadata=extra_meta, quality=int(quality) if quality else None
                )
                db.add(q)
                db.commit()
                st.success("已写入数据库（questions 表）。")
            except Exception:
                db.rollback()
                st.error(f"写入失败：{traceback.format_exc()}")
            finally: db.close()

with right_col:
    st.header("题库浏览 / 搜索 / 分页")
    db = SessionLocal()
    try:
        col_filter_1, col_filter_2, col_filter_3 = st.columns(3)
        with col_filter_1: course_id_filter = st.number_input("课程 ID 过滤", 0, key="f_course_id")
        with col_filter_2: grade_id_filter = st.number_input("年级 ID 过滤", 0, key="f_grade_id")
        with col_filter_3: chapter_id_filter = st.number_input("章节 ID 过滤", 0, key="f_chapter_id")
        type_filter = st.text_input("题型过滤")
        diff_min, diff_max = st.slider("难度范围", 1, 5, (1,5))
        quality_min, quality_max = st.slider("质量范围", 1, 5, (1,5))
        keyword = st.text_input("按标题或内容关键字搜索")
        query = db.query(Question)
        filters = []
        if course_id_filter > 0: filters.append(Question.course_id == course_id_filter)
        if grade_id_filter > 0: filters.append(Question.grade_id == grade_id_filter)
        if chapter_id_filter > 0: filters.append(Question.chapter_id == chapter_id_filter)
        if type_filter.strip(): filters.append(Question.question_type.ilike(f"%{type_filter.strip()}%"))
        filters.append(Question.difficulty.between(diff_min, diff_max))
        filters.append(Question.quality.between(quality_min, quality_max))
        if keyword.strip():
            kw = f"%{keyword.strip()}%"
            filters.append(or_(Question.title.ilike(kw), Question.content_md.ilike(kw), Question.content_latex.ilike(kw)))
        if filters: query = query.filter(and_(*filters))
        page_size = st.number_input("每页显示数量", 5, 200, 10, 5)
        total = query.count()
        total_pages = max(1, math.ceil(total / page_size))
        page = st.number_input(f"页码 (1 - {total_pages})", 1, total_pages, 1)
        offset = (page - 1) * page_size
        records = query.order_by(Question.id.desc()).offset(offset).limit(page_size).all()
        st.write(f"共 {total} 条匹配记录 — 第 {page} / {total_pages} 页")
        
        for r in records:
            with st.expander(f"ID {r.id}  | 标题: {r.title or '(无)'}"):
                st.markdown(f"**课程 ID:** {r.course_id} | **年级 ID:** {r.grade_id} | **章节 ID:** {r.chapter_id} | **题型:** {r.question_type} | **难度:** {r.difficulty} | **质量:** {r.quality}")
                st.markdown("**Markdown 预览:**")
                rendered_record_md = render_markdown_with_images(r.content_md or "", WORD_PARTS_FOLDER)
                st.markdown(rendered_record_md, unsafe_allow_html=True)
                st.markdown("**LaTeX (raw):**")
                st.code((r.content_latex or "")[:2000], language="latex")
                st.markdown("**额外 metadata:**")
                st.json(r.extra_metadata or {})
                if st.button(f"✏️ 编辑此题 (ID {r.id})", key=f"edit_btn_{r.id}"):
                    st.session_state["edit_id"] = r.id
                    st.rerun()

        if "edit_id" in st.session_state:
            edit_id = st.session_state["edit_id"]
            instance = db.query(Question).filter(Question.id == edit_id).first()
            if instance:
                st.markdown("---")
                st.subheader(f"编辑题目 ID: {edit_id}")
                e_title = st.text_input("标题", value=instance.title or "", key=f"e_title_{edit_id}")
                col_e_1, col_e_2, col_e_3 = st.columns(3)
                with col_e_1: e_course_id = st.number_input("课程 ID", 0, value=instance.course_id or 0, key=f"e_course_{edit_id}")
                with col_e_2: e_grade_id = st.number_input("年级 ID", 0, value=instance.grade_id or 0, key=f"e_grade_{edit_id}")
                with col_e_3: e_chapter_id = st.number_input("章节 ID", 0, value=instance.chapter_id or 0, key=f"e_chapter_{edit_id}")
                e_type = st.text_input("题型", value=instance.question_type or "", key=f"e_type_{edit_id}")
                e_difficulty = st.number_input("难度", 1, 5, value=instance.difficulty or 3, key=f"e_diff_{edit_id}")
                e_quality = st.number_input("质量", 1, 5, value=instance.quality or 3, key=f"e_qual_{edit_id}")
                e_answer = st.text_input("答案", value=instance.answer or "", key=f"e_ans_{edit_id}")
                e_analysis = st.text_area("解析", value=instance.analysis or "", key=f"e_anal_{edit_id}")
                e_kp = st.text_input("知识点", value=",".join(instance.knowledge_points or []), key=f"e_kp_{edit_id}")
                e_meta_raw = st.text_area("额外 metadata JSON", value=json.dumps(instance.extra_metadata or {}, ensure_ascii=False), key=f"e_meta_{edit_id}")
                
                if st.button("💾 保存修改", key=f"e_save_{edit_id}"):
                    try:
                        kp_list = [kp.strip() for kp in e_kp.split(",")] if e_kp.strip() else None
                        try: e_meta_parsed = json.loads(e_meta_raw.replace("\\", "/"))
                        except Exception: e_meta_parsed = instance.extra_metadata or {}
                        instance.title = e_title or None
                        instance.course_id = e_course_id if e_course_id > 0 else None
                        instance.grade_id = e_grade_id if e_grade_id > 0 else None
                        instance.chapter_id = e_chapter_id if e_chapter_id > 0 else None
                        instance.question_type = e_type or None
                        instance.difficulty = int(e_difficulty) if e_difficulty else None
                        instance.quality = int(e_quality) if e_quality else None
                        instance.answer = e_answer or None
                        instance.analysis = e_analysis or None
                        instance.knowledge_points = kp_list
                        instance.extra_metadata = e_meta_parsed
                        db.commit()
                        st.success("保存成功")
                        del st.session_state["edit_id"]
                        st.rerun() 
                    except Exception as e:
                        db.rollback()
                        st.error(f"保存失败: {e}")
            else:
                st.warning("未找到该记录")
                del st.session_state["edit_id"]
    except Exception as e:
        st.error(f"查询失败：{e}")
        st.exception(traceback.format_exc())
    finally:
        if db.is_active and 'edit_id' not in st.session_state:
            db.close()