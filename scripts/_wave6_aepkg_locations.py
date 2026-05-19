import os
import pathlib
import collections

root = pathlib.Path(r"C:\Users\example-user\<workspace>\aepkit")
parents = collections.Counter()
for dirpath, dirnames, _ in os.walk(root):
    for d in list(dirnames):
        if d == ".git":
            dirnames.remove(d)
            continue
    for d in dirnames:
        if d.endswith(".aepkg"):
            parent = str(pathlib.Path(dirpath).relative_to(root)).replace("\\", "/")
            parents[parent] += 1

for p, n in parents.most_common(25):
    print(f"{n:5} {p}")
print(f"\nTOTAL .aepkg/ dirs: {sum(parents.values())}")
