import sys
import os
import tkinter as tk
import time

# Ensure workspace root is on sys.path so we can import gui_ollama_chat from tools/ script
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from gui_ollama_chat import OllamaGUI

root = tk.Tk()
app = OllamaGUI(root)

sample = (
    "This is a simulated final merged answer.\n\n"
    "- Point A: concise summary.\n"
    "- Point B: additional notes.\n\n"
    "End of simulated final."
)
try:
    app.queue.put(('merged_final', sample))
except Exception:
    pass

# process a few event loop cycles to let the app create popup
for _ in range(10):
    root.update()
    time.sleep(0.05)

# keep GUI open for interactive inspection
root.mainloop()
