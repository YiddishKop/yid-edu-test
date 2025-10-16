import streamlit as st
import psycopg2
from collections import defaultdict

# --- 1. 数据库连接配置 (请根据您的实际情况修改) ---
DB_CONFIG = {
    "dbname": "exam_db",
    "user": "yiddi",              # 您的 PostgreSQL 用户名
    "password": "020297",  # 您的数据库密码
    "host": "localhost",
    "port": "5432"
}

# --- 2. 设置页面标题和布局 ---
st.set_page_config(page_title="知识库浏览器", layout="wide")
st.title("📚 Exam DB 知识库目录树")

# --- 3. 从数据库获取所有数据的函数 ---
def get_full_knowledge_tree():
    """
    一次性从数据库中查询所有教材、章节、小节和知识点，并构建一个层级字典。
    """
    query = """
    SELECT
        t.id AS textbook_id,
        t.name AS textbook_name,
        c.id AS chapter_id,
        c.name AS chapter_name,
        s.id AS section_id,
        s.name AS section_name,
        kp.point_name
    FROM
        textbooks t
    LEFT JOIN
        chapters c ON t.id = c.textbook_id
    LEFT JOIN
        sections s ON c.id = s.chapter_id
    LEFT JOIN
        sections_knowledge_points skp ON s.id = skp.section_id
    LEFT JOIN
        knowledge_points kp ON skp.point_id = kp.id
    ORDER BY
        t.name, c.name, s.name, kp.point_name;
    """
    
    tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                results = cur.fetchall()
                
                for row in results:
                    tb_id, tb_name, ch_id, ch_name, sec_id, sec_name, kp_name = row
                    
                    if tb_id and ch_id and sec_id and kp_name:
                        # 确保知识点不重复添加
                        if kp_name not in tree[tb_name][ch_name][sec_name]:
                            tree[tb_name][ch_name][sec_name].append(kp_name)
                    elif tb_id and ch_id and sec_id:
                        # 确保节存在，即使它没有知识点
                        tree[tb_name][ch_name][sec_name] = tree[tb_name][ch_name].get(sec_name, [])
                    elif tb_id and ch_id:
                        # 确保章存在，即使它没有节
                        tree[tb_name][ch_name] = tree[tb_name].get(ch_name, {})
                    elif tb_id:
                        # 确保教材存在
                        tree[tb_name] = tree.get(tb_name, {})

    except psycopg2.OperationalError as e:
        st.error(f"数据库连接失败，请检查您的配置: {e}")
        return None
    except Exception as e:
        st.error(f"查询数据时发生错误: {e}")
        return None
        
    return tree

# --- 4. 渲染目录树 ---
knowledge_tree = get_full_knowledge_tree()

if knowledge_tree:
    # 按教材名称排序
    sorted_textbooks = sorted(knowledge_tree.keys())

    for textbook_name in sorted_textbooks:
        with st.expander(f"📖 **{textbook_name}**"):
            
            chapters = knowledge_tree.get(textbook_name, {})
            if not chapters:
                st.write("本教材下暂无章节。")
                continue

            sorted_chapters = sorted(chapters.keys())
            for chapter_name in sorted_chapters:
                with st.expander(f"📄 **{chapter_name}**"):
                    
                    sections = chapters.get(chapter_name, {})
                    if not sections:
                        st.write("本章下暂无小节。")
                        continue

                    sorted_sections = sorted(sections.keys())
                    for section_name in sorted_sections:
                        with st.expander(f"🖋️ {section_name}"):
                            
                            knowledge_points = sections.get(section_name, [])
                            if knowledge_points:
                                for kp in sorted(knowledge_points):
                                    st.markdown(f"- {kp}")
                            else:
                                st.info("本节下暂未关联知识点。")
else:
    st.warning("未能加载知识库数据。")