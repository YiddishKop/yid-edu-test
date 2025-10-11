# app.py
import streamlit as st
import json
import math
import io
import traceback

from sqlalchemy import (
    create_engine, Column, Integer, Text, String,
    TIMESTAMP, ARRAY, func, and_, or_
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Optional libraries for parsing/convert (try imports, provide fallback)
try:
    import docx  # python-docx
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

# ===============================
# 1) Config - 请根据你的环境修改
# ===============================
DB_USER = "yiddi"          # ← 改成你的用户名
DB_PASSWORD = "020297"  # ← 改成你的密码
DB_NAME = "exam_db"            # ← 改成你的 DB 名
DB_HOST = "localhost"
DB_PORT = "5432"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 简易登录配置（示例），生产环境请替换为真实认证方案
AUTH_USERS = {
    "admin": "admin123"  # username: password （明文示例，仅用于演示）
}

# ===============================
# 2) DB init
# ===============================
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ===============================
# 3) ORM model (严格映射你提供的表)
#    注意：数据库列名是 metadata，但 ORM 属性不能用 metadata，因此映射为 extra_metadata
# ===============================
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

    # 数据库列名仍然是 metadata，但 ORM 使用 extra_metadata 属性
    extra_metadata = Column("metadata", JSONB)

    created_at = Column(
        TIMESTAMP,
        server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )


# 不要调用 Base.metadata.create_all(bind=engine) —— 你已经手工建表


# ===============================
# 4) 工具函数：解析上传文件
# ===============================
def parse_docx_bytes(file_bytes):
    if docx is None:
        raise RuntimeError("python-docx 未安装，请 pip install python-docx")
    stream = io.BytesIO(file_bytes)
    document = docx.Document(stream)
    paras = []
    for p in document.paragraphs:
        text = p.text.strip()
        if text:
            paras.append(text)
    return "\n\n".join(paras)


def parse_pdf_bytes(file_bytes):
    if pdfplumber is None:
        raise RuntimeError("pdfplumber 未安装，请 pip install pdfplumber")
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
        return "% (Warning: pypandoc or pandoc not installed) \n" + md_text
    try:
        latex = pypandoc.convert_text(md_text, 'latex', format='md')
        return latex
    except Exception as e:
        return "% (pandoc convert failed) \n" + md_text


# ===============================
# 5) 登录管理
# ===============================
def login_widget():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user = None

    if not st.session_state.logged_in:
        st.sidebar.title("🔒 登录")
        username = st.sidebar.text_input("用户名", key="login_username")
        password = st.sidebar.text_input("密码", type="password", key="login_password")
        if st.sidebar.button("登录", key="login_btn"):
            if username in AUTH_USERS and AUTH_USERS[username] == password:
                st.session_state.logged_in = True
                st.session_state.user = username
                st.rerun()
            else:
                st.sidebar.error("用户名或密码错误")
        st.sidebar.markdown("——")
        st.sidebar.info("示例账号：admin / admin123 （请替换为安全策略）")
        return False
    else:
        st.sidebar.success(f"已登录：{st.session_state.user}")
        if st.sidebar.button("登出", key="logout_btn"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()
        return True


# ===============================
# 6) UI 布局
# ===============================
st.set_page_config(page_title="题库管理（增强版）", layout="wide")
st.title("📚 题库管理（增强版）")

logged_in = login_widget()
if not logged_in:
    st.stop()

left_col, right_col = st.columns([3, 2])

# ===============================
# 左侧：上传 / Markdown 编辑 / LaTeX 编辑 / 预览 / 保存
# ===============================
with left_col:
    st.header("📄 上传 & 编辑区")

    # 上传支持 md/txt/docx/pdf
    uploaded = st.file_uploader("上传 .md / .txt / .docx / .pdf", type=["md", "txt", "docx", "pdf"])

    # 临时 buffer 保存上传内容
    if uploaded is not None:
        raw_bytes = uploaded.read()
        fname = uploaded.name.lower()
        try:
            if fname.endswith(".docx"):
                uploaded_buffer = parse_docx_bytes(raw_bytes)
            elif fname.endswith(".pdf"):
                uploaded_buffer = parse_pdf_bytes(raw_bytes)
            elif fname.endswith(".md") or fname.endswith(".txt"):
                uploaded_buffer = raw_bytes.decode("utf-8")
            else:
                uploaded_buffer = raw_bytes.decode("utf-8", errors="ignore")
        except Exception as e:
            st.error(f"解析文件失败: {e}")
            uploaded_buffer = ""
        # 保存到 session_state 临时变量
        st.session_state["uploaded_buffer"] = uploaded_buffer

    # 初始化 markdown_buffer
    if "markdown_buffer" not in st.session_state:
        st.session_state["markdown_buffer"] = st.session_state.get("uploaded_buffer", "")

    # 上传覆盖按钮
    if st.button("以上传内容覆盖编辑区"):
        if "uploaded_buffer" in st.session_state:
            st.session_state.markdown_buffer = st.session_state["uploaded_buffer"]

    # Markdown 编辑与预览
    st.subheader("1) Markdown 编辑与预览")
    md_text = st.text_area("Markdown 编辑", value=st.session_state.get("markdown_buffer", ""), height=260)
    st.session_state.markdown_buffer = md_text

    st.markdown("**Markdown 预览：**")
    st.markdown(md_text, unsafe_allow_html=False)

    st.markdown("---")

    # Markdown -> LaTeX 自动转换（即时）
    try:
        auto_latex = md_to_latex(md_text)
    except Exception as e:
        auto_latex = "% (convert error) \n" + str(e)

    # LaTeX 编辑与预览
    st.subheader("2) LaTeX 编辑与预览 （可手动修改）")
    if "latex_buffer" not in st.session_state:
        st.session_state.latex_buffer = auto_latex

    if st.button("用自动生成的 LaTeX 覆盖编辑区"):
        st.session_state.latex_buffer = auto_latex

    latex_text = st.text_area("LaTeX 编辑", value=st.session_state.get("latex_buffer", ""), height=260)
    st.session_state.latex_buffer = latex_text

    st.markdown("**LaTeX 预览（MathJax 渲染数学公式）**")
    st.code(latex_text[:1000] + ("..." if len(latex_text) > 1000 else ""), language="latex")
    try:
        st.latex(latex_text)
    except Exception:
        st.info("LaTeX 预览仅渲染数学公式，复杂 TeX 文档请使用编译工具验证。")

    st.markdown("---")

    # 结构化元信息输入
    st.subheader("3) 结构化元信息（将写入对应字段）")
    title = st.text_input("题目标题或简述", value="")
    course = st.text_input("课程", value="")
    grade = st.text_input("年级", value="")
    chapter = st.text_input("章节", value="")
    q_type = st.text_input("题目类型（单选/多选/解答）", value="")
    difficulty = st.number_input("难度（1-5）", min_value=1, max_value=5, value=3)
    answer = st.text_input("答案", value="")
    analysis = st.text_area("解析", value="")
    knowledge_raw = st.text_input("知识点（用逗号分隔）", value="")
    meta_raw = st.text_area("额外 metadata JSON（可选）", value="{\"source\": \"期中卷\", \"year\": 2024}")

    # 保存按钮
    if st.button("✅ 确认并写入题库"):
        db = SessionLocal()
        try:
            # 解析 extra metadata
            extra_meta = {}
            if meta_raw and meta_raw.strip():
                try:
                    extra_meta = json.loads(meta_raw.replace("\\", "/"))
                except Exception:
                    st.warning("额外 metadata 不是有效 JSON，已存空对象。")

            kp_list = [kp.strip() for kp in knowledge_raw.split(",")] if knowledge_raw.strip() else []

            new_q = Question(
                title=title or None,
                content_md=md_text or None,
                content_latex=latex_text or None,
                course=course or None,
                grade=grade or None,
                chapter=chapter or None,
                knowledge_points=kp_list if kp_list else None,
                question_type=q_type or None,
                difficulty=int(difficulty) if difficulty else None,
                answer=answer or None,
                analysis=analysis or None,
                extra_metadata=extra_meta
            )
            db.add(new_q)
            db.commit()
            st.success("✅ 已成功写入数据库（questions 表）")
            st.session_state.markdown_buffer = md_text
            st.session_state.latex_buffer = latex_text
        except Exception as e:
            db.rollback()
            st.error(f"写入失败：{e}")
        finally:
            db.close()


# ===============================
# 右侧：搜索 / 分页 / 编辑
# ===============================
with right_col:
    st.header("🔎 题库浏览 / 搜索 / 分页")
    db = SessionLocal()
    try:
        # 搜索过滤控件
        course_filter = st.text_input("课程过滤", value="", key="filter_course")
        grade_filter = st.text_input("年级过滤", value="", key="filter_grade")
        type_filter = st.text_input("题型过滤", value="", key="filter_type")
        diff_min, diff_max = st.slider("难度范围", 1, 5, (1, 5), key="filter_diff")
        keyword = st.text_input("按标题或内容关键字搜索", value="", key="filter_keyword")

        # 构造查询
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

        # 分页
        page_size = st.number_input("每页显示数量", min_value=5, max_value=200, value=10, step=5, key="page_size")
        total = query.count()
        total_pages = max(1, math.ceil(total / page_size))
        page = st.number_input(f"页码 (1 - {total_pages})", min_value=1, max_value=total_pages, value=1, key="page_num")
        offset = (page - 1) * page_size

        records = query.order_by(Question.id.desc()).offset(offset).limit(page_size).all()
        st.write(f"共 {total} 条匹配记录 — 第 {page} / {total_pages} 页")

        for r in records:
            with st.expander(f"ID {r.id}  | 标题: {r.title or '(无标题)'}"):
                st.markdown(f"**课程:** {r.course}   | **年级:** {r.grade}   | **题型:** {r.question_type}   | **难度:** {r.difficulty}")
                st.markdown("**Markdown (preview):**")
                st.markdown(r.content_md or "", unsafe_allow_html=False)
                st.markdown("**LaTeX (raw):**")
                st.code((r.content_latex or "")[:2000], language="latex")
                st.markdown("**额外 metadata:**")
                st.json(r.extra_metadata or {})

                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button(f"✏️ 编辑此题 (ID {r.id})", key=f"edit_btn_{r.id}"):
                        st.session_state["edit_id"] = r.id
                with col2:
                    if st.button(f"🗑 删除此题 (ID {r.id})", key=f"delete_btn_{r.id}"):
                        # 点击按钮时，先设置 session_state 标记待删除 ID
                        st.session_state["delete_id"] = r.id
                        
                # 页面底部或右侧单独显示删除确认
        if "delete_id" in st.session_state:
            del_id = st.session_state["delete_id"]
            st.warning(f"⚠️ 你确定要删除题目 ID {del_id} 吗？此操作不可撤销。")
            confirm = st.button("确认删除", key=f"confirm_delete_{del_id}")
            cancel = st.button("取消删除", key=f"cancel_delete_{del_id}")
        
            if confirm:
                try:
                    db.query(Question).filter(Question.id == del_id).delete()
                    db.commit()
                    st.success(f"题目 ID {del_id} 已删除")
                    del st.session_state["delete_id"]
                    # st.experimental_rerun()  # 刷新页面
                    st.rerun()  # 刷新页面
                except Exception as e:
                    db.rollback()
                    st.error(f"删除失败: {e}")
        
            if cancel:
                del st.session_state["delete_id"]
                st.info("已取消删除")

        # 编辑单条记录
        if "edit_id" in st.session_state:
            edit_id = st.session_state["edit_id"]
            instance = db.query(Question).filter(Question.id == edit_id).first()
            if instance:
                st.subheader(f"编辑题目 ID: {edit_id}")
                e_title = st.text_input("标题", value=instance.title or "", key=f"title_edit_{edit_id}")
                e_course = st.text_input("课程", value=instance.course or "", key=f"course_edit_{edit_id}")
                e_grade = st.text_input("年级", value=instance.grade or "", key=f"grade_edit_{edit_id}")
                e_chapter = st.text_input("章节", value=instance.chapter or "", key=f"chapter_edit_{edit_id}")
                e_type = st.text_input("题型", value=instance.question_type or "", key=f"type_edit_{edit_id}")
                e_difficulty = st.number_input("难度", min_value=1, max_value=5, value=instance.difficulty or 3, key=f"difficulty_edit_{edit_id}")
                e_answer = st.text_input("答案", value=instance.answer or "", key=f"answer_edit_{edit_id}")
                e_analysis = st.text_area("解析", value=instance.analysis or "", key=f"analysis_edit_{edit_id}")
                e_kp = st.text_input("知识点（逗号分隔）", value=",".join(instance.knowledge_points or []), key=f"kp_edit_{edit_id}")
                e_meta_raw = st.text_area("额外 metadata JSON", value=json.dumps(instance.extra_metadata or {}, ensure_ascii=False), key=f"meta_edit_{edit_id}")

                if st.button("💾 保存修改", key=f"save_edit_{edit_id}"):
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
                st.warning("未找到该记录，可能已被删除")
                del st.session_state["edit_id"]

    except Exception as e:
        st.error(f"查询失败: {e}")
        st.exception(traceback.format_exc())
    finally:
        db.close()
