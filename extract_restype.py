from pathlib import Path

res_path_name = "arknights_mower/resources/"
res_path = Path(res_path_name)

data = "from typing import Literal\n\nRes = Literal[\n"
references = {}

for i in res_path.glob("**/*.png"):
    res_name = i.as_posix()
    res_name = res_name.replace(res_path_name, "")
    res_name = res_name.replace(".png", "")
    data += f'    "{res_name}",\n'
    references[res_name] = []

data += "]\n"

with open("arknights_mower/utils/typealias/res.py", "w", encoding="utf-8") as f:
    f.write(data)

for py_file in Path("arknights_mower").glob("**/*.py"):
    posix_path = py_file.as_posix()
    if posix_path == "arknights_mower/utils/typealias/res.py":
        continue
    with py_file.open("r", encoding="utf-8") as f:
        content = f.read()
    for name, matches in references.items():
        if name in content:
            matches.append(posix_path)

for name, matches in references.items():
    if len(matches) > 0:
        print(name)
        for m in matches:
            print(f"    {m}")
for name, matches in references.items():
    if len(matches) == 0:
        print(f"[WARN]{name}")

