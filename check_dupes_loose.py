
import re
from collections import Counter

file_path = "d:\\QuizBot\\test.txt"
with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

numbers = []
# Relaxed: Number at start, maybe followed by space, maybe dot/bracket
re_q = re.compile(r'^(\d+)\s*[\.\)]?\s+') 
# Added \s+ to ensure it's a number followed by space or text, to avoid matching just "481" if it's junk.
# Actually, 74Boshlang'ich doesn't have a space! So \s*

re_q_loose = re.compile(r'^(\d+)')

for i, line in enumerate(lines):
    t = line.strip()
    if not t: continue
    
    # We want to catch 74Boshlang'ich too
    m = re_q_loose.match(t)
    if m:
        num = int(m.group(1))
        # Basic heuristic: question numbers are usually small and not years
        if num < 1000:
            numbers.append(num)

counts = Counter(numbers)
dupes = {n: c for n, c in counts.items() if c > 1}

print(f"Total numbered lines (loose): {len(numbers)}")
print(f"Unique numbers: {len(counts)}")
if dupes:
    print(f"Duplicates found: {dupes}")

# Check for specific numbers
for n in [74, 150, 265, 306, 356]:
    if n in counts:
        print(f"Number {n} found {counts[n]} times.")
    else:
        print(f"Number {n} still NOT found.")
