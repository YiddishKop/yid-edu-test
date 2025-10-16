import json
import os
import sys

# ----------------------------------------------------
# 阶段 I: LaTeX 模板定义 (使用最简 \hbox 隔离)
# ----------------------------------------------------

# 纯英文基础模板
LATEX_HEADER = r"""
\documentclass[12pt, a4paper]{article}
\usepackage{amsmath, amssymb}
\usepackage{geometry}
\geometry{a4paper, margin=1in}

\pagestyle{empty}
\begin{document}
\begin{center}
    \textbf{\Large Automated Exam (MVP English Version)} 
\end{center}
\vspace{0.5cm}
"""

LATEX_FOOTER = r"""
\end{document}
"""

# 使用 \hbox{} 代替 \parbox，并手动格式化
QUIZ_TEMPLATE_RAW = r"""
\vspace{0.5cm}
\noindent\textbf{\large Question. %s} (ID: %s)\par 
\noindent
\hbox{
%s
}
\vspace{0.5cm}
"""

SOLUTION_TEMPLATE_RAW = r"""
\vspace{0.5cm}
\noindent\textbf{\large Solution. %s} (ID: %s)
\par
\textbf{Answer:} %s \\ 
\textbf{Explanation:} %s
\vspace{0.5cm}
"""

# ----------------------------------------------------
# 阶段 II: 核心生成函数 (最简字符串拼接，无正则，无 $ 替换)
# ----------------------------------------------------

def generate_latex_from_json(json_file_path):
    """读取 JSON 并生成 LaTeX 文件的核心函数。"""
    
    data = None 
    
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"FATAL ERROR: File read or JSON parsing failed. Details: {e}", file=sys.stderr)
        return

    if data is None:
        return

    exam_content = []
    solution_content = []
    
    for i, quiz in enumerate(data['quiz_list']):
        quiz_id = quiz['quiz_id']
        question_num = str(i + 1) 
        
        question_latex = quiz['question_latex']
        solution_latex = quiz['solution_latex']
        answer = quiz['answer']
        
        # 1. 确保 % 符号被转义 (这是唯一的 Python 修复)
        question_latex = question_latex.replace('%', '%%') 
        solution_latex = solution_latex.replace('%', '%%')

        # 2. 使用 .replace() 替换 %s 占位符 (最简单的字符串操作)
        
        # QUIZ 模板的拼接逻辑：(Question Num, ID, Content)
        quiz_template = QUIZ_TEMPLATE_RAW
        quiz_template = quiz_template.replace('%s', question_num, 1)
        quiz_template = quiz_template.replace('%s', quiz_id, 1)
        quiz_template = quiz_template.replace('%s', question_latex, 1)
        exam_content.append(quiz_template)
        
        # SOLUTION 模板的拼接逻辑：(Question Num, ID, Answer, Solution)
        solution_template = SOLUTION_TEMPLATE_RAW
        solution_template = solution_template.replace('%s', question_num, 1)
        solution_template = solution_template.replace('%s', quiz_id, 1)
        solution_template = solution_template.replace('%s', answer, 1)
        solution_template = solution_template.replace('%s', solution_latex, 1)
        solution_content.append(solution_template)


# ----------------------------------------------------
# 阶段 III: 文件写入 (移除 UTF-8 编码参数)
# ----------------------------------------------------
    
    final_latex_exam = LATEX_HEADER + "\n".join(exam_content) + LATEX_FOOTER
    final_latex_solution = LATEX_HEADER + "\n".join(solution_content) + LATEX_FOOTER
    
    # 【核心修正】移除 encoding='utf-8'，使用默认的 ASCII 兼容编码
    with open('exam_mvp.tex', 'w') as f:
        f.write(final_latex_exam)
        
    with open('solution_mvp.tex', 'w') as f:
        f.write(final_latex_solution)

    success_message = "✅ Successfully generated exam_mvp.tex and solution_mvp.tex (Pure ASCII Test)."
    sys.stdout.buffer.write(success_message.encode('utf-8'))
    sys.stdout.buffer.write(b'\n')

# ... (保持 IV 阶段的调用逻辑不变)

# ----------------------------------------------------
# 阶段 IV: 数据写入和执行逻辑 (保持英文数据)
# ----------------------------------------------------

JSON_PATH = 'master_quiz_data.json'

if __name__ == "__main__":
    quiz_data = {
      "test_id": "EXAM_MVP_2025",
      "quiz_list": [
        {
          "quiz_id": "Q_CALC001",
          "question_type": "CALCULUS",
          "question_latex": "Find the derivative of $f(x)=x^2+1$ at $x=2$. (Weight: 0.8)",
          "solution_latex": "$$\\text{Sol: } f'(x) = 2x$$$$\\text{At } x=2 \\text{, } f'(2) = 4$$",
          "answer": "$$4$$"
        },
        {
          "quiz_id": "Q_GEO002",
          "question_type": "GEOMETRY",
          "question_latex": "Given the radius of a circle $r=5$, find its area.",
          "solution_latex": "$$\\text{Sol: } A = \\pi r^2 = 25\\pi$$",
          "answer": "$$25\\pi$$"
        }
      ]
    }
    
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(quiz_data, f, ensure_ascii=False, indent=2)

    generate_latex_from_json(JSON_PATH)