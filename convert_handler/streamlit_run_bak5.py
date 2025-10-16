# app.py
import streamlit as st
import json
import io
import os
import tempfile
import subprocess
import traceback
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, Integer, Text, String,
    TIMESTAMP, ARRAY, func, and_, or_
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
# Config - 修改为你的环境
# ===============================
DB_USER = "yiddi"          # ← 改成你的用户名
DB_PASSWORD = "020297"  # ← 改成你的密码
DB_NAME = "exam_db"            # ← 改成你的 DB 名
DB_HOST = "localhost"
DB_PORT = "5432"

# xelatex 命令（若不在 PATH，可以写完整路径）
XELATEX_CMD = "xelatex"
# dvisvgm 命令
DVISVGM_CMD = "dvisvgm"

# 默认使用 SVG 输出
RENDER_FORMAT = "svg"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 简易登录（仅示例）
AUTH_USERS = {"admin": "admin123"}

# ===============================
# DB init & ORM（与你表结构对应）
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
    course = Column(String(50))
    grade = Column(String(20))
    chapter = Column(String(100))
    knowledge_points = Column(ARRAY(Text))
    question_type = Column(String(50))
    difficulty = Column(Integer)
    answer = Column(Text)
    analysis = Column(Text)
    extra_metadata = Column("metadata", JSONB)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

# ===============================
# Helpers: parse files, md->latex
# ===============================
def parse_docx_bytes(file_bytes):
    if docx is None:
        raise RuntimeError("python-docx 未安装，请 pip install python-docx")
    stream = io.BytesIO(file_bytes)
    document = docx.Document(stream)
    paras = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    return "\n\n".join(paras)

def parse_pdf_bytes(file_bytes):
    if pdfplumber is None:
        raise RuntimeError("pdfplumber 未安装，请 pip install pdfplumber")
    pdfplumber.pdf.PDFPage.images_backend = "mutool"

    stream = io.BytesIO(file_bytes)
    texts = []
    with pdfplumber.open(stream) as pdf:
        for page in pdf.pages:
            txt = page.extract_text()
            if txt:
                texts.append(txt)
    return "\n\n".join(texts)

def md_to_latex(md_text):
    if not md_text:
        return ""
    if pypandoc is None:
        # 如果 pypandoc 不可用，保留 md 原文但标注
        return "% (Warning: pypandoc not installed) \n" + md_text
    try:
        return pypandoc.convert_text(md_text, 'latex', format='md')
    except Exception:
        return "% (pandoc convert failed) \n" + md_text

# ===============================
# LaTeX -> SVG (xelatex + dvisvgm)
# ===============================
def latex_full_document_body(user_tex: str):
    """
    把用户的 LaTeX 片段封装成完整的 tex 文档，使用 xelatex + xeCJK 以支持中文。
    user_tex: 期望用户已写好必要的数学段落和文本（可以包含中文）
    """
    preamble = r"""
\documentclass[12pt]{article}
\usepackage{amsmath,amssymb}
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{SimSun} % 如果没有 SimSun，会使用系统默认 CJK 字体
\pagestyle{empty}
\parindent=0pt
\begin{document}
"""
    ending = r"""
\end{document}
"""
    return preamble + user_tex + ending

def compile_latex_to_svg(tex_body: str, timeout=20):
    """
    将 tex_body 写到临时目录，使用 xelatex 编译为 PDF，然后用 dvisvgm --pdf 转为 SVG。
    返回 (success: bool, svg_text_or_error_log: str)
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        tex_file = td_path / "preview.tex"
        pdf_file = td_path / "preview.pdf"
        svg_file = td_path / "preview.svg"
        log_file = td_path / "latex.log"

        tex_file.write_text(tex_body, encoding="utf-8")

        # 运行 xelatex（-interaction=nonstopmode -halt-on-error）
        # 写出到 cwd 临时目录，capture stdout/stderr
        try:
            proc = subprocess.run(
                [XELATEX_CMD, "-interaction=nonstopmode", "-halt-on-error", str(tex_file.name)],
                cwd=td,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout
            )
        except subprocess.TimeoutExpired as e:
            return False, f"XeLaTeX 超时（>{timeout}s）。"

        # xelatex 会生成 preview.pdf（若失败，查看 .log / stdout）
        stdout = proc.stdout.decode("utf-8", errors="ignore")
        stderr = proc.stderr.decode("utf-8", errors="ignore")

        # 检查是否生成 pdf
        if not pdf_file.exists():
            # 尝试从 .log 文件读取错误
            logs = stdout + "\n" + stderr
            # 有时 xelatex 会创建 preview.log or preview.log
            # 读取生成的 .log（如果有）
            for path in td_path.glob("*.log"):
                try:
                    logs += "\n\n==== LOG: " + str(path.name) + " ====\n"
                    logs += path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass
            return False, f"XeLaTeX 编译失败：\n{logs}"

        # 使用 dvisvgm 将 PDF 转为 SVG
        # dvisvgm 支持 --pdf 输入
        try:
            proc2 = subprocess.run(
                [DVISVGM_CMD, "--pdf", str(pdf_file.name), "-n", "-o", str(svg_file.name)],
                cwd=td,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10
            )
            out2 = proc2.stdout.decode("utf-8", errors="ignore")
            err2 = proc2.stderr.decode("utf-8", errors="ignore")
        except subprocess.TimeoutExpired:
            return False, "dvisvgm 超时。"

        if not svg_file.exists():
            # 返回 dvisvgm 错误信息和 xelatex 日志
            logs = stdout + "\n" + stderr + "\n\nDVISVGM:\n" + out2 + "\n" + err2
            return False, f"dvisvgm 转换失败：\n{logs}"

        # 读取 svg 内容并返回
        svg_text = svg_file.read_text(encoding="utf-8", errors="ignore")
        return True, svg_text

# ===============================
# Login widget
# ===============================
def login_widget():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user = None
    if not st.session_state.logged_in:
        st.sidebar.title("🔒 登录")
        username = st.sidebar.text_input("用户名")
        password = st.sidebar.text_input("密码", type="password")
        if st.sidebar.button("登录"):
            if username in AUTH_USERS and AUTH_USERS[username] == password:
                st.session_state.logged_in = True
                st.session_state.user = username
                st.rerun()
            else:
                st.sidebar.error("用户名或密码错误")
        st.sidebar.info("示例账号：admin / admin123 （请替换为安全方案）")
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
            if name.endswith(".docx"):
                default_md = parse_docx_bytes(raw)
            elif name.endswith(".pdf"):
                default_md = parse_pdf_bytes(raw)
            elif name.endswith(".md") or name.endswith(".txt"):
                default_md = raw.decode("utf-8")
            else:
                default_md = raw.decode("utf-8", errors="ignore")
        except Exception as e:
            st.error(f"解析文件失败：{e}")
            default_md = ""

    st.subheader("1) Markdown 编辑与预览")
    if "markdown_buffer" not in st.session_state:
        st.session_state.markdown_buffer = default_md
    if uploaded is not None and st.button("以上传内容覆盖编辑区"):
        st.session_state.markdown_buffer = default_md

    md_text = st.text_area("Markdown 编辑", value=st.session_state.get("markdown_buffer",""), height=220)
    st.session_state.markdown_buffer = md_text
    st.markdown("**Markdown 预览：**")
    st.markdown(md_text, unsafe_allow_html=False)

    st.markdown("---")
    # Markdown -> LaTeX
    auto_latex = md_to_latex(md_text)

    st.subheader("2) LaTeX 编辑（基于 Markdown 自动生成）")
    if "latex_buffer" not in st.session_state:
        st.session_state.latex_buffer = auto_latex
    if st.button("用自动生成的 LaTeX 覆盖编辑区"):
        st.session_state.latex_buffer = auto_latex

    latex_text = st.text_area("LaTeX 编辑", value=st.session_state.get("latex_buffer",""), height=260)
    st.session_state.latex_buffer = latex_text

    st.markdown("**3) 精确 LaTeX 预览（XeLaTeX + dvisvgm -> SVG）**")
    col_preview_buttons, col_preview_display = st.columns([1,4])
    with col_preview_buttons:
        if st.button("生成精确预览 (编译 LaTeX)"):
            # 封装 tex 文档并编译
            doc = latex_full_document_body(latex_text)
            success, result = compile_latex_to_svg(doc, timeout=25)
            st.session_state._latex_preview_success = success
            st.session_state._latex_preview_result = result
    # show preview or errors
    if "_latex_preview_result" in st.session_state:
        if st.session_state._latex_preview_success:
            svg_code = st.session_state._latex_preview_result
            # embed svg (ensure svg content is raw)
            components.html(svg_code, height=300)
        else:
            st.error("LaTeX 编译或转换失败，以下为错误日志：")
            st.text(st.session_state._latex_preview_result[:10000])

    st.markdown("---")
    st.subheader("4) 结构化元信息（将写入字段）")
    title = st.text_input("题目标题或简述")
    course = st.text_input("课程")
    grade = st.text_input("年级")
    chapter = st.text_input("章节")
    q_type = st.text_input("题目类型（单选/多选/解答）")
    difficulty = st.number_input("难度（1-5）", min_value=1, max_value=5, value=3)
    answer = st.text_input("答案")
    analysis = st.text_area("解析")
    kp_raw = st.text_input("知识点（逗号分隔）")
    meta_raw = st.text_area("额外 metadata JSON（可选）", value="")

    if st.button("✅ 确认 LaTeX 并写入数据库"):
        # 如果没有成功生成精确预览，应提醒用户先生成并确认
        if not st.session_state.get("_latex_preview_success", False):
            st.warning("请先点击“生成精确预览 (编译 LaTeX)”并确认渲染结果无误，再保存。")
        else:
            db = SessionLocal()
            try:
                # parse meta JSON safely
                extra_meta = {}
                if meta_raw.strip():
                    try:
                        extra_meta = json.loads(meta_raw.replace("\\","/"))
                    except Exception:
                        st.warning("额外 metadata 不是合法 JSON，已存空对象。")
                        extra_meta = {}
                kp_list = [kp.strip() for kp in kp_raw.split(",")] if kp_raw.strip() else None
                q = Question(
                    title=title or None,
                    content_md=md_text or None,
                    content_latex=latex_text or None,
                    course=course or None,
                    grade=grade or None,
                    chapter=chapter or None,
                    knowledge_points=kp_list,
                    question_type=q_type or None,
                    difficulty=int(difficulty) if difficulty else None,
                    answer=answer or None,
                    analysis=analysis or None,
                    extra_metadata=extra_meta
                )
                db.add(q)
                db.commit()
                st.success("已写入数据库（questions 表）。")
            except Exception as e:
                db.rollback()
                st.error(f"写入失败：{e}")
                st.exception(traceback.format_exc())
            finally:
                db.close()

with right_col:
    st.header("题库浏览 / 搜索 / 分页")
    db = SessionLocal()
    try:
        course_filter = st.text_input("课程过滤")
        grade_filter = st.text_input("年级过滤")
        type_filter = st.text_input("题型过滤")
        diff_min, diff_max = st.slider("难度范围", 1, 5, (1,5))
        keyword = st.text_input("按标题或内容关键字搜索")

        query = db.query(Question)
        filters = []
        if course_filter.strip():
            filters.append(Question.course.ilike(f"%{course_filter.strip()}%"))
        if grade_filter.strip():
            filters.append(Question.grade.ilike(f"%{grade_filter.strip()}%"))
        if type_filter.strip():
            filters.append(Question.question_type.ilike(f"%{type_filter.strip()}%"))
        if diff_min is not None:
            filters.append(Question.difficulty >= diff_min)
        if diff_max is not None:
            filters.append(Question.difficulty <= diff_max)
        if keyword.strip():
            kw = f"%{keyword.strip()}%"
            filters.append(or_(Question.title.ilike(kw),
                               Question.content_md.ilike(kw),
                               Question.content_latex.ilike(kw)))
        if filters:
            query = query.filter(and_(*filters))

        page_size = st.number_input("每页显示数量", min_value=5, max_value=200, value=10, step=5)
        total = query.count()
        total_pages = max(1, math.ceil(total / page_size))
        page = st.number_input(f"页码 (1 - {total_pages})", min_value=1, max_value=total_pages, value=1)
        offset = (page - 1) * page_size
        records = query.order_by(Question.id.desc()).offset(offset).limit(page_size).all()

        st.write(f"共 {total} 条匹配记录 — 第 {page} / {total_pages} 页")
        for r in records:
            with st.expander(f"ID {r.id}  | 标题: {r.title or '(无)'}"):
                st.markdown(f"**课程:** {r.course} | **年级:** {r.grade} | **题型:** {r.question_type} | **难度:** {r.difficulty}")
                st.markdown("**Markdown 预览:**")
                st.markdown(r.content_md or "", unsafe_allow_html=False)
                st.markdown("**LaTeX (raw):**")
                st.code((r.content_latex or "")[:2000], language="latex")
                st.markdown("**额外 metadata:**")
                st.json(r.extra_metadata or {})
                if st.button(f"✏️ 编辑此题 (ID {r.id})"):
                    st.session_state["edit_id"] = r.id

        if "edit_id" in st.session_state:
            edit_id = st.session_state["edit_id"]
            instance = db.query(Question).filter(Question.id == edit_id).first()
            if instance:
                st.markdown("---")
                st.subheader(f"编辑题目 ID: {edit_id}")
                e_title = st.text_input("标题", value=instance.title or "")
                e_course = st.text_input("课程", value=instance.course or "")
                e_grade = st.text_input("年级", value=instance.grade or "")
                e_chapter = st.text_input("章节", value=instance.chapter or "")
                e_type = st.text_input("题型", value=instance.question_type or "")
                e_difficulty = st.number_input("难度", min_value=1, max_value=5, value=instance.difficulty or 3)
                e_answer = st.text_input("答案", value=instance.answer or "")
                e_analysis = st.text_area("解析", value=instance.analysis or "")
                e_kp = st.text_input("知识点（逗号分隔）", value=",".join(instance.knowledge_points or []))
                e_meta_raw = st.text_area("额外 metadata JSON", value=json.dumps(instance.extra_metadata or {}, ensure_ascii=False))
                if st.button("💾 保存修改"):
                    try:
                        kp_list = [kp.strip() for kp in e_kp.split(",")] if e_kp.strip() else None
                        try:
                            e_meta_parsed = json.loads(e_meta_raw.replace("\\", "/"))
                        except Exception:
                            e_meta_parsed = instance.extra_metadata or {}
                        instance.title = e_title or None
                        instance.course = e_course or None
                        instance.grade = e_grade or None
                        instance.chapter = e_chapter or None
                        instance.question_type = e_type or None
                        instance.difficulty = int(e_difficulty) if e_difficulty else None
                        instance.answer = e_answer or None
                        instance.analysis = e_analysis or None
                        instance.knowledge_points = kp_list
                        instance.extra_metadata = e_meta_parsed
                        db.commit()
                        st.success("保存成功")
                        del st.session_state["edit_id"]
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
        db.close()
