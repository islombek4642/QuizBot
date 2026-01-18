
import re
from collections import Counter

file_path = "d:\\QuizBot\\test.txt"
with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

numbers = []
re_q = re.compile(r'^(\d+)[\.\)]')
for line in lines:
    m = re_q.match(line.strip())
    if m:
        numbers.append(int(m.group(1)))

counts = Counter(numbers)
dupes = {n: c for n, c in counts.items() if c > 1}

print(f"Total numbered lines: {len(numbers)}")
print(f"Unique numbers: {len(counts)}")
if dupes:
    print(f"Duplicates found: {dupes}")
else:
    print("No duplicates found.")

# Let's check if there are lines that match re_q but ARE NOT questions (e.g. inside options)
# Our parser ONLY checks at the start of a line.

# Also, check if any questions were parsed but NOT numbered? 
# In _parse_abc_format, it ONLY starts a question on m_q.
# So len(questions) should equal len(numbers).
# Wait, my analyze_numbers said:
# Total question numbers found in raw text: 476 (this was len(set(numbers)))
# Parsed 479 questions.
# This means there are 479 numbered lines in the file!

# Let's see which numbers appear 479 times.
# 479 - 476 = 3.
# So there should be 3 duplicates.
