import json

log_path = "/root/.gemini/antigravity/brain/b6b2a2a3-a414-473b-b2b1-c80fa7b8f417/.system_generated/logs/overview.txt"

with open(log_path, "r") as f:
    lines = f.readlines()

for log_line in lines:
    if "The following changes were made by the USER to: " not in log_line:
        continue
    try:
        data = json.loads(log_line)
        content = data.get("content", "")

        # Split content into lines
        c_lines = content.split("\n")

        file_path = None
        in_diff = False
        diff_lines = []

        for i, line in enumerate(c_lines):
            if line.startswith("The following changes were made by the USER to: "):
                file_path = line.split("to: ")[1].split(". If ")[0]
            elif line.strip() == "[diff_block_start]":
                in_diff = True
            elif line.strip() == "[diff_block_end]":
                in_diff = False
                if file_path and diff_lines:
                    restored_lines = []
                    for dl in diff_lines:
                        if dl.startswith("-") and not dl.startswith("---"):
                            restored_lines.append(dl[1:])
                        elif dl.startswith(" ") or not dl:
                            restored_lines.append(dl[1:] if dl else "")

                    print(f"Writing to {file_path}")
                    with open(file_path, "w") as out:
                        out.write("\n".join(restored_lines))
                file_path = None
                diff_lines = []
            elif in_diff:
                if not line.startswith("@@"):
                    diff_lines.append(line)

    except Exception as e:
        print(f"Error: {e}")
