# streamlit_run_corrected_v3.py
import streamlit as st
import json
import io
import traceback
from pathlib import Path
import re
import base64
import streamlit.components.v1 as components

from sqlalchemy import (
    create_engine, Column, Integer, Text, String,
    TIMESTAMP, ARRAY, func, and_, or_, SmallInteger, text, Table, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base

# ===============================
# Config (Please fill in your password)
# ===============================
DB_USER = "yiddi"
DB_PASSWORD = "your_password"  # <--- Please enter your correct database password here
DB_NAME = "exam_db"
DB_HOST = "localhost"
DB_PORT = "5432"
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
AUTH_USERS = {"admin": "admin123"}

# ===============================
# DB init & ORM
# ===============================
# ✅ **FIX**: Added client_encoding='utf8' to resolve connection encoding issues on Windows
engine = create_engine(DATABASE_URL, client_encoding='utf8')
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# --- ORM Model Definitions ---
sections_knowledge_points_table = Table('sections_knowledge_points', Base.metadata,
    Column('section_id', Integer, ForeignKey('sections.id'), primary_key=True),
    Column('point_id', Integer, ForeignKey('knowledge_points.id'), primary_key=True)
)

class Textbook(Base):
    __tablename__ = "textbooks"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    course_id = Column(Integer)
    grade_id = Column(Integer)
    chapters = relationship("Chapter", back_populates="textbook")

class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    textbook_id = Column(Integer, ForeignKey('textbooks.id'))
    textbook = relationship("Textbook", back_populates="chapters")
    sections = relationship("Section", back_populates="chapter")

class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    chapter_id = Column(Integer, ForeignKey('chapters.id'))
    chapter = relationship("Chapter", back_populates="sections")
    knowledge_points = relationship("KnowledgePoint", secondary=sections_knowledge_points_table, back_populates="sections")

class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    id = Column(Integer, primary_key=True)
    point_name = Column(String, unique=True)
    sections = relationship("Section", secondary=sections_knowledge_points_table, back_populates="knowledge_points")

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text)
    content_md = Column(Text)
    content_latex = Column(Text)
    course_id = Column(Integer)
    grade_id = Column(Integer)
    chapter_id = Column(Integer)
    section_id = Column(Integer)
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
# Helper Functions
# ===============================
def parse_uploaded_file(uploaded_file):
    if uploaded_file is None: return ""
    try:
        content = io.BytesIO(uploaded_file.getvalue())
        name = uploaded_file.name.lower()
        if name.endswith(".docx"):
            import docx
            document = docx.Document(content)
            return "\n\n".join([p.text.strip() for p in document.paragraphs if p.text.strip()])
        elif name.endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(content) as pdf:
                return "\n\n".join([page.extract_text() for page in pdf.pages if page.extract_text() or ""])
        else:
            return uploaded_file.getvalue().decode("utf-8")
    except Exception as e:
        st.error(f"解析文件 '{uploaded_file.name}' 失败: {e}")
        return ""

def md_to_latex(md_text):
    if not md_text: return ""
    try:
        import pypandoc
        latex_output = pypandoc.convert_text(md_text, 'latex', format='md')
        return re.sub(r'\\pandocbounded{(.*?)}', r'\1', latex_output, flags=re.DOTALL)
    except Exception:
        return f"% Pandoc conversion failed. Using raw markdown.\n{md_text}"

# ===============================
# Database Query Functions
# ===============================
@st.cache_data(ttl=600)
def get_textbooks_from_db():
    with SessionLocal() as session:
        return session.query(Textbook.name, Textbook.id).order_by(Textbook.name).all()

@st.cache_data(ttl=600)
def get_chapters_for_textbook(textbook_id: int):
    if not textbook_id: return []
    with SessionLocal() as session:
        return session.query(Chapter.name, Chapter.id).filter(Chapter.textbook_id == textbook_id).order_by(Chapter.name).all()

@st.cache_data(ttl=600)
def get_sections_for_chapter(chapter_id: int):
    if not chapter_id: return []
    with SessionLocal() as session:
        return session.query(Section.name, Section.id).filter(Section.chapter_id == chapter_id).order_by(Section.name).all()

@st.cache_data(ttl=600)
def get_kps_for_section(section_id: int):
    if not section_id: return []
    with SessionLocal() as session:
        kps = session.query(KnowledgePoint.point_name).join(
            sections_knowledge_points_table
        ).filter(
            sections_knowledge_points_table.c.section_id == section_id
        ).order_by(KnowledgePoint.point_name).all()
        return [kp[0] for kp in kps]

@st.cache_data(ttl=3600)
def get_enum_labels(enum_type_name: str):
    query = text(f"""
        SELECT e.enumlabel
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = :type_name
        ORDER BY e.enumsortorder;
    """)
    try:
        with SessionLocal() as session:
            result = session.execute(query, {'type_name': enum_type_name}).fetchall()
            return [row[0] for row in result]
    except Exception:
        return ["single_choice", "multiple_choice", "fill_in_the_blank", "essay"]

# ===============================
# App UI
# ===============================
st.set_page_config(page_title="题库管理系统", layout="wide")
st.title("📚 题库管理系统")

# Initialize Session State
if "content_md" not in st.session_state: st.session_state.content_md = ""
if "content_latex" not in st.session_state: st.session_state.content_latex = ""
if "answer_md" not in st.session_state: st.session_state.answer_md = ""
if "analysis_md" not in st.session_state: st.session_state.analysis_md = ""

left_col, right_col = st.columns(2)

# --- Left Column: Question Content & Metadata ---
with left_col:
    st.header("1. 题干编辑")
    uploaded_content = st.file_uploader("上传题干文件", type=["md", "txt", "pdf", "docx"], key="content_uploader")
    if uploaded_content:
        st.session_state.content_md = parse_uploaded_file(uploaded_content)
        st.session_state.content_latex = md_to_latex(st.session_state.content_md)

    st.text_area("题干 Markdown", key="content_md", height=200)
    if st.button("由 Markdown 生成 LaTeX 题干"):
        st.session_state.content_latex = md_to_latex(st.session_state.content_md)
    st.text_area("题干 LaTeX", key="content_latex", height=200)

    st.header("2. 题目元信息")
    title = st.text_input("题目标题或简述")

    all_textbooks = get_textbooks_from_db()
    book_options = {name: id for name, id in all_textbooks}
    selected_book_name = st.selectbox("选择教材", options=book_options.keys())
    selected_book_id = book_options.get(selected_book_name)

    chapter_options = {}
    if selected_book_id:
        all_chapters = get_chapters_for_textbook(selected_book_id)
        chapter_options = {name: id for name, id in all_chapters}
    selected_chapter_name = st.selectbox("选择章节", options=chapter_options.keys())
    selected_chapter_id = chapter_options.get(selected_chapter_name)

    section_options = {}
    if selected_chapter_id:
        all_sections = get_sections_for_chapter(selected_chapter_id)
        section_options = {name: id for name, id in all_sections}
    selected_section_name = st.selectbox("选择小节", options=section_options.keys())
    selected_section_id = section_options.get(selected_section_name)

    kp_options = []
    if selected_section_id:
        kp_options = get_kps_for_section(selected_section_id)
    selected_kps = st.multiselect("关联知识点", options=kp_options)

    col1, col2 = st.columns(2)
    with col1:
        question_type_options = get_enum_labels('question_type_enum')
        q_type = st.selectbox("题目类型", options=question_type_options)
        difficulty = st.slider("难度", 1, 5, 3)
    with col2:
        quality = st.slider("题目质量", 1, 5, 3)
        meta_raw = st.text_area("额外元数据 (JSON格式)", value="{}")

# --- Right Column: Answer & Analysis ---
with right_col:
    st.header("3. 答案与解析")
    st.subheader("答案")
    uploaded_answer = st.file_uploader("上传答案文件", type=["md", "txt", "pdf", "docx"], key="answer_uploader")
    if uploaded_answer:
        st.session_state.answer_md = parse_uploaded_file(uploaded_answer)
    st.text_area("答案内容", key="answer_md", height=100)
    
    st.markdown("---")
    
    st.subheader("解析")
    uploaded_analysis = st.file_uploader("上传解析文件", type=["md", "txt", "pdf", "docx"], key="analysis_uploader")
    if uploaded_analysis:
        st.session_state.analysis_md = parse_uploaded_file(uploaded_analysis)
    st.text_area("解析 Markdown", key="analysis_md", height=220)

    st.markdown("---")
    st.header("4. 提交到数据库")
    if st.button("✅ 确认并写入数据库", use_container_width=True, type="primary"):
        try:
            extra_meta_dict = json.loads(meta_raw) if meta_raw.strip() else {}
            
            with SessionLocal() as session:
                selected_textbook = session.get(Textbook, selected_book_id) if selected_book_id else None
                
                new_question = Question(
                    title=title or None,
                    content_md=st.session_state.content_md or None,
                    content_latex=st.session_state.content_latex or None,
                    course_id=selected_textbook.course_id if selected_textbook else None,
                    grade_id=selected_textbook.grade_id if selected_textbook else None,
                    chapter_id=selected_chapter_id,
                    section_id=selected_section_id,
                    knowledge_points=selected_kps or None,
                    question_type=q_type or None,
                    difficulty=int(difficulty),
                    answer=st.session_state.answer_md or None,
                    analysis=st.session_state.analysis_md or None,
                    extra_metadata=extra_meta_dict,
                    quality=int(quality)
                )
                session.add(new_question)
                session.commit()
                st.success(f"题目 '{title or '(无标题)'}' 已成功写入数据库！")

        except Exception as e:
            st.error(f"写入数据库失败：{e}")
            traceback.print_exc()