import json

nb = json.load(open("development/local/search/search.ipynb"))
# find where artifacts dataframe is printed
for cell in nb["cells"]:
    if "artifacts = client.execute_tasks" in "".join(cell["source"]):
        print("FOUND cell")
        for o in cell.get("outputs", []):
            if "data" in o and "text/html" in o["data"]:
                print(o["data"]["text/html"][:1000])
