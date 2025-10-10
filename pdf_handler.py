import re
text = open("output.txt","r",encoding="utf8").read()
parts = re.split(r'(?m)^\s*\d+[．.]', text)
for i, s in enumerate(parts, 1):
    filename = f"pdf_part_{i}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(s)