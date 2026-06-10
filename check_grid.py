import json

# read notebook outputs or run the logic
# since I can't easily get the dataframe from notebook without running it,
# I'll parse the notebook to see what they printed!
nb = json.load(open("development/local/search/search.ipynb"))
for cell in nb["cells"]:
    if "Detected a true spatial layout" in "".join(cell.get("source", [])):
        for o in cell.get("outputs", []):
            if "text" in o:
                print("".join(o["text"]))
