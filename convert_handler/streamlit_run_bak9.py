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
    TIMESTAMP, ARRAY, func, and_, or_, SmallInteger, text
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

def md_to_latex(md_text):
    if not md_text: return ""
    if pypandoc is None: return f"% (Warning: pypandoc not installed) \n{md_text}"
    try:
        latex_output = pypandoc.convert_text(md_text, 'latex', format='md')
        cleaned_latex = re.sub(r'\\pandocbounded{(.*?)}', r'\1', latex_output, flags=re.DOTALL)
        return cleaned_latex
    except Exception as e:
        return f"% (pandoc convert failed: {e}) \n{md_text}"

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
        except subprocess.TimeoutExpired: return False, "dvisvgm 超时。"
        if not svg_file.exists():
            out2 = proc2.stdout.decode("utf-8", errors="ignore")
            err2 = proc2.stderr.decode("utf-8", errors="ignore")
            return False, f"dvisvgm 转换失败：\n{out2}\n{err2}"
        return True, svg_file.read_text(encoding="utf-8", errors="ignore")

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
            # 清理所有会话状态以避免数据混淆
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        return True

# ===============================
# App UI
# ===============================
st.set_page_config(page_title="题库管理系统", layout="wide")
st.title("题库管理系统")

if not login_widget():
    st.stop()

left_col, middle_col, right_col = st.columns([2.5, 2.5, 2])

# --- 左栏：负责题干 ---
with left_col:
    st.header("1. 题干编辑区")
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

    if "content_md_buffer" not in st.session_state: st.session_state.content_md_buffer = default_md
    if uploaded is not None and st.button("用上传内容覆盖题干"): st.session_state.content_md_buffer = default_md

    md_text = st.text_area("题干 Markdown", value=st.session_state.content_md_buffer, height=220, key="content_md_editor")
    st.markdown("**题干 Markdown 预览：**")
    rendered_html_md = render_markdown_with_images(md_text, WORD_PARTS_FOLDER)
    st.markdown(rendered_html_md, unsafe_allow_html=True)

    st.markdown("---")
    auto_latex = md_to_latex(md_text)
    if "content_latex_buffer" not in st.session_state: st.session_state.content_latex_buffer = auto_latex
    if st.button("自动生成 LaTeX 题干"): st.session_state.content_latex_buffer = auto_latex
    latex_text = st.text_area("题干 LaTeX", value=st.session_state.content_latex_buffer, height=260, key="content_latex_editor")

    st.markdown("**题干 LaTeX 精确预览**")
    if st.button("编译题干 LaTeX"):
        image_base_path = Path(WORD_PARTS_FOLDER)
        doc = latex_full_document_body(latex_text, image_base_path)
        success, result = compile_latex_to_svg(doc, timeout=25)
        st.session_state._content_preview_success = success
        st.session_state._content_preview_result = result
    
    if "_content_preview_result" in st.session_state:
        if st.session_state._content_preview_success:
            components.html(st.session_state._content_preview_result, height=300, scrolling=True)
        else:
            st.error("题干 LaTeX 编译失败：")
            st.text(st.session_state._content_preview_result[:10000])

    st.markdown("---")
    st.header("3. 题目元信息")
    title = st.text_input("题目标题或简述")
    col_ids_1, col_ids_2, col_ids_3 = st.columns(3)
    
    # ✅ [修改] 使用 text() 包装器执行原生 SQL
    db_session = SessionLocal()
    try:
        query = text("SELECT e.enumlabel FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid WHERE t.typname = 'question_type_enum' ORDER BY e.enumsortorder")
        result = db_session.execute(query).fetchall()
        allowed_types = [row[0] for row in result]
    finally:
        db_session.close()

    with col_ids_1: course_id = st.number_input("课程 ID", min_value=0, value=0, step=1)
    with col_ids_2: grade_id = st.number_input("年级 ID", min_value=0, value=0, step=1)
    with col_ids_3: chapter_id = st.number_input("章节 ID", min_value=0, value=0, step=1)
    
    q_type = st.selectbox("题目类型", options=allowed_types)
    difficulty = st.number_input("难度（1-5）", 1, 5, 3)
    quality = st.number_input("题目质量 (1-5)", 1, 5, 3)
    kp_raw = st.text_input("知识点（逗号分隔）")
    meta_raw = st.text_area("额外 metadata JSON（可选）", value="{}")

# --- 中栏：负责答案和解析 ---
with middle_col:
    st.header("2. 答案与解析编辑区")
    
    st.subheader("答案")
    if "answer_buffer" not in st.session_state: st.session_state.answer_buffer = ""
    answer_text = st.text_area("答案内容", value=st.session_state.answer_buffer, height=100, key="answer_editor")
    
    st.markdown("---")

    st.subheader("解析")
    if "analysis_md_buffer" not in st.session_state: st.session_state.analysis_md_buffer = ""
    analysis_md_text = st.text_area("解析 Markdown", value=st.session_state.analysis_md_buffer, height=220, key="analysis_md_editor")
    st.markdown("**解析 Markdown 预览：**")
    rendered_analysis_md = render_markdown_with_images(analysis_md_text, WORD_PARTS_FOLDER)
    st.markdown(rendered_analysis_md, unsafe_allow_html=True)
    
    st.markdown("---")
    auto_analysis_latex = md_to_latex(analysis_md_text)
    if "analysis_latex_buffer" not in st.session_state: st.session_state.analysis_latex_buffer = auto_analysis_latex
    if st.button("自动生成 LaTeX 解析"): st.session_state.analysis_latex_buffer = auto_analysis_latex
    analysis_latex_text = st.text_area("解析 LaTeX", value=st.session_state.analysis_latex_buffer, height=260, key="analysis_latex_editor")

    st.markdown("**解析 LaTeX 精确预览**")
    if st.button("编译解析 LaTeX"):
        image_base_path = Path(WORD_PARTS_FOLDER)
        doc = latex_full_document_body(analysis_latex_text, image_base_path)
        success, result = compile_latex_to_svg(doc, timeout=25)
        st.session_state._analysis_preview_success = success
        st.session_state._analysis_preview_result = result

    if "_analysis_preview_result" in st.session_state:
        if st.session_state._analysis_preview_success:
            components.html(st.session_state._analysis_preview_result, height=300, scrolling=True)
        else:
            st.error("解析 LaTeX 编译失败：")
            st.text(st.session_state._analysis_preview_result[:10000])

# --- 提交按钮放在中栏底部 ---
with middle_col:
    st.markdown("---")
    st.header("4. 提交操作")
    if st.button("✅ 确认并写入数据库", use_container_width=True):
        if not st.session_state.get("_content_preview_success", False):
            st.warning("请先成功编译“题干 LaTeX”再保存。")
        else:
            db = SessionLocal()
            try:
                extra_meta = {}
                if meta_raw.strip():
                    try: extra_meta = json.loads(meta_raw.replace("\\","/"))
                    except Exception: st.warning("额外 metadata 不是合法 JSON，已存空对象。")
                kp_list = [kp.strip() for kp in kp_raw.split(",")] if kp_raw.strip() else None
                
                q = Question(
                    title=title or None,
                    content_md=st.session_state.content_md_editor or None,
                    content_latex=st.session_state.content_latex_editor or None,
                    course_id=course_id if course_id > 0 else None,
                    grade_id=grade_id if grade_id > 0 else None,
                    chapter_id=chapter_id if chapter_id > 0 else None,
                    knowledge_points=kp_list,
                    question_type=q_type or None,
                    difficulty=int(difficulty) if difficulty else None,
                    answer=st.session_state.answer_editor or None,
                    analysis=st.session_state.analysis_md_editor or None,
                    extra_metadata=extra_meta,
                    quality=int(quality) if quality else None
                )
                db.add(q)
                db.commit()
                st.success("已写入数据库（questions 表）。")
            except Exception:
                db.rollback()
                st.error(f"写入失败：{traceback.format_exc()}")
            finally: db.close()

# --- 右栏：负责浏览 ---
with right_col:
    st.header("题库浏览")
    db = SessionLocal()
    try:
        course_id_filter = st.number_input("课程 ID 过滤", 0, key="f_course_id")
        type_filter = st.selectbox("题型过滤", options=[""] + allowed_types, key="f_type")
        keyword = st.text_input("关键字搜索 (标题/内容)")
        
        query = db.query(Question)
        filters = []
        if course_id_filter > 0: filters.append(Question.course_id == course_id_filter)
        if type_filter: filters.append(Question.question_type == type_filter)
        if keyword.strip():
            kw = f"%{keyword.strip()}%"
            filters.append(or_(Question.title.ilike(kw), Question.content_md.ilike(kw)))
        if filters: query = query.filter(and_(*filters))
        
        page_size = st.number_input("每页显示", 5, 200, 10, 5)
        total = query.count()
        total_pages = max(1, math.ceil(total / page_size))
        page = st.number_input(f"页码 (1-{total_pages})", 1, total_pages, 1)
        offset = (page - 1) * page_size
        records = query.order_by(Question.id.desc()).offset(offset).limit(page_size).all()
        
        st.write(f"共 {total} 条记录 — 第 {page}/{total_pages} 页")
        
        for r in records:
            with st.expander(f"ID {r.id} | {r.title or '(无标题)'}"):
                st.markdown(f"**类型:** {r.question_type} | **难度:** {r.difficulty} | **质量:** {r.quality}")
                st.markdown("**题干预览:**")
                rendered_record_md = render_markdown_with_images(r.content_md or "", WORD_PARTS_FOLDER)
                st.markdown(rendered_record_md, unsafe_allow_html=True)
                st.markdown("**答案:**")
                st.info(r.answer or "无")
                st.markdown("**解析预览:**")
                rendered_record_analysis = render_markdown_with_images(r.analysis or "", WORD_PARTS_FOLDER)
                st.markdown(rendered_record_analysis, unsafe_allow_html=True)

                if st.button(f"✏️ 加载此题进行编辑 (ID {r.id})", key=f"edit_btn_{r.id}"):
                    st.session_state.content_md_buffer = r.content_md or ""
                    st.session_state.content_latex_buffer = r.content_latex or ""
                    st.session_state.answer_buffer = r.answer or ""
                    st.session_state.analysis_md_buffer = r.analysis or ""
                    st.session_state.analysis_latex_buffer = md_to_latex(r.analysis or "")
                    
                    st.session_state.pop('_content_preview_result', None)
                    st.session_state.pop('_analysis_preview_result', None)

                    st.info(f"ID {r.id} 的数据已加载到左侧和中间的编辑区。")
                    st.rerun()

    except Exception as e:
        st.error(f"查询失败：{e}")
        st.exception(traceback.format_exc())
    finally:
        if db.is_active:
            db.close()