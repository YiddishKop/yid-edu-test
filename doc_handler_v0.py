import re
text = open("有理数五大概念.md","r",encoding="utf8").read()
# 匹配 “例x” 或 “针对练习x” 作为分题点
parts = re.split(r'【例\d+】|针对练习\d+', text)
for i, s in enumerate(parts, 1):
    filename = f"part_{i}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(s)