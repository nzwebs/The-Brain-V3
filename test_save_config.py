import tkinter as tk
import os, json
from gui_ollama_chat import OllamaGUI

root = tk.Tk()
root.withdraw()
app = OllamaGUI(root)
# set test URLs
try:
    app.a_url.set("http://localhost:11434")
except Exception:
    try:
        app.a_url.insert(0, "http://localhost:11434")
    except Exception:
        pass
try:
    app.b_url.set("http://localhost:11435")
except Exception:
    try:
        app.b_url.insert(0, "http://localhost:11435")
    except Exception:
        pass
ok = app.save_config()
path = os.path.join(os.path.dirname(__file__), "gui_config.json")
print("SAVE_OK", ok)
if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("CONFIG_EXISTS", path)
    print("a_url=", data.get("a_url"))
    print("b_url=", data.get("b_url"))
else:
    print("CONFIG_MISSING")
try:
    root.destroy()
except Exception:
    pass
