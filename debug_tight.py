import matplotlib.pyplot as plt

fig, axes = plt.subplots(50, 50, figsize=(100, 100))
try:
    plt.tight_layout()
    plt.savefig("test_tight.png")
    print("Success")
except Exception:
    import traceback

    traceback.print_exc()
