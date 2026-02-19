import sys, os
import tkinter as tk
# Ensure workspace root is on sys.path so imports work when running from tools/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from gui_ollama_chat import OllamaGUI

# Create a hidden Tk root so OllamaGUI can initialize widgets
root = tk.Tk()
root.withdraw()
app = OllamaGUI(root)
app.memory_enabled.set(True)

samples = [
    "My name is Alex",
    "I live in Seattle",
    "I work as a teacher",
    "I love pizza",
]
for s in samples:
    app._add_facts_from_text(s)

print('Memory summary:', app._get_memory_summary())

p = app._brain_path()
if p and __name__ == '__main__':
    try:
        with open(p, 'r', encoding='utf-8') as f:
            print('--- brain.json ---')
            print(f.read())
    except Exception as e:
        print('Failed to read brain.json:', e)

root.destroy()
