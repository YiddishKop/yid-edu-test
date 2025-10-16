.PHONY: all clean

LATEX_COMPILER = xelatex -interaction=nonstopmode 
JSON_FILE = master_quiz_data.json
# 注意：不需要在 clean 目标中使用 $(JSON_FILE)

# --- 编译目标 (Targets) ---
all: exam_mvp.pdf solution_mvp.pdf

# 依赖：生成 PDF 依赖于 .tex 文件
%.pdf: %.tex
	$(LATEX_COMPILER) $<
	$(LATEX_COMPILER) $<  # 运行两次以确保交叉引用正确

# 依赖：生成 .tex 文件依赖于 Python 脚本和 JSON 数据
exam_mvp.tex solution_mvp.tex: $(JSON_FILE) latex_compiler.py
	export PYTHONIOENCODING=utf-8; \
	python3 latex_compiler.py $(JSON_FILE)

# --- 清理目标 (Clean Target) ---
# 只删除编译过程中生成的文件，不删除源代码 master_quiz_data.json
clean:
	rm -f *.pdf *.tex *.aux *.log *.out