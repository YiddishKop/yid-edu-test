-- PostgreSQL schema for yid-edu-test (minimal, app-compatible)

-- Textbooks / Chapters / Sections / Knowledge Points
CREATE TABLE IF NOT EXISTS textbooks (
  id SERIAL PRIMARY KEY,
  name TEXT,
  course_id INTEGER,
  grade_id INTEGER,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chapters (
  id SERIAL PRIMARY KEY,
  name TEXT,
  textbook_id INTEGER REFERENCES textbooks(id) ON DELETE SET NULL,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sections (
  id SERIAL PRIMARY KEY,
  name TEXT,
  chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_points (
  id SERIAL PRIMARY KEY,
  point_name TEXT UNIQUE,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sections_knowledge_points (
  section_id INTEGER REFERENCES sections(id) ON DELETE CASCADE,
  point_id INTEGER REFERENCES knowledge_points(id) ON DELETE CASCADE,
  PRIMARY KEY (section_id, point_id)
);


-- Questions (match ORM in streamlit_view/streamlit_run.py)
CREATE TABLE IF NOT EXISTS questions (
  id SERIAL PRIMARY KEY,
  title TEXT,
  content_md TEXT,
  content_latex TEXT,
  course_id INTEGER,
  grade_id INTEGER,
  chapter_id INTEGER,
  section_id INTEGER,
  knowledge_points TEXT[],
  question_type VARCHAR(50),
  difficulty INTEGER,
  answer TEXT,
  analysis TEXT,
  metadata JSONB,
  quality SMALLINT,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_questions_course ON questions(course_id);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(question_type);
CREATE INDEX IF NOT EXISTS idx_questions_created ON questions(created_at);
