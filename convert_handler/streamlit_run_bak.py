import streamlit as st
import json
from sqlalchemy import (
    create_engine, Column, Integer, Text, String,
    TIMESTAMP, ARRAY, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ===============================
# ✅ 1. 数据库配置（改成你的账号密码）
# ===============================
DB_USER = "yiddi"          # ← 改成你的
DB_PASSWORD = "020297"  # ← 改成你的
DB_NAME = "exam_db"            # ← 你的库名
DB_HOST = "localhost"          # 或实际IP
DB_PORT = "5432"

DATABASE_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# ===============================
# ✅ 2. ORM 模型（完全对应你建的表）
# ===============================
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

    extra_metadata = Column("metadata",JSONB)

    created_at = Column(
        TIMESTAMP,
        server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )

# ❌ 3. 不要 create_all(), 因为表已建好
# Base.metadata.create_all(bind=engine)  # ← 已移除


# ===============================
# ✅ 4. Streamlit 主体
# ===============================
st.set_page_config(page_title="题库管理系统", layout="wide")

left_col, right_col = st.columns([2, 3])

# -------- 左侧：上传 & 入库 --------
with left_col:
    st.header("📄 上传并解析题目")

    uploaded_file = st.file_uploader(
        "上传 .md 或 .txt 文件（内容将写入 content_md / content_latex）",
        type=["md", "txt"]
    )

    if uploaded_file:
        file_content = uploaded_file.read().decode("utf-8")
        st.subheader("文件内容预览")
        st.code(file_content, language="latex")

        # 补充元数据
        st.write("填写题目信息：")
        q_title = st.text_input("题目标题或简述", "")
        q_course = st.text_input("课程（如 math）", "")
        q_grade = st.text_input("年级（如 高一）", "")
        q_chapter = st.text_input("章节（如 第三章）", "")
        q_type = st.text_input("题目类型（单选/多选/解答）", "")
        q_difficulty = st.number_input("难度（1-5）", min_value=1, max_value=5, value=3)
        q_answer = st.text_input("答案（可选）", "")
        q_analysis = st.text_area("解析（可选）", "")
        q_knowledge_raw = st.text_area("知识点数组输入（用逗号分隔）", "")

        # JSONB 可选
        meta_raw = st.text_area(
            "额外元信息 JSON（如 {\"source\":\"2024模拟卷\"}）", ""
        )

        if st.button("✅ 写入数据库"):
            db = SessionLocal()
            try:
                metadata_dict = {}
                if meta_raw.strip():
                    try:
                        metadata_dict = json.loads(meta_raw)
                    except:
                        st.warning("metadata 不是有效 JSON，将存空对象。")
                        metadata_dict = {}

                knowledge_points = (
                    [kp.strip() for kp in q_knowledge_raw.split(",")]
                    if q_knowledge_raw.strip() else []
                )

                new_question = Question(
                    title=q_title,
                    content_md=file_content,
                    content_latex=file_content,  # 如后期需要转换可在此处理
                    course=q_course,
                    grade=q_grade,
                    chapter=q_chapter,
                    knowledge_points=knowledge_points,
                    question_type=q_type,
                    difficulty=q_difficulty,
                    answer=q_answer,
                    analysis=q_analysis,
                    metadata=metadata_dict
                )
                db.add(new_question)
                db.commit()
                st.success("✅ 写入成功！")
            except Exception as e:
                db.rollback()
                st.error(f"写入失败：{e}")
            finally:
                db.close()


# -------- 右侧：查看数据 --------
with right_col:
    st.header("📚 数据库题目查看")

    db = SessionLocal()
    try:
        records = db.query(Question).all()
        if not records:
            st.info("当前没有题目记录。")
        else:
            for q in records:
                st.write(f"### ID: {q.id}  | 标题: {q.title}")
                st.code(q.content_latex or "", language="latex")
                st.json(q.metadata)
                st.markdown("---")
    except Exception as e:
        st.error(f"查询失败：{e}")
    finally:
        db.close()
