import os, sys
import tkinter as tk
# ensure project root on path
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
from gui_ollama_chat import OllamaGUI

# Path to captured real-run output (created by prior run)
captured = r"c:\Users\nzweb\AppData\Roaming\Code\User\workspaceStorage\ccdf4bc8ab2d6b23669c7dacb835dfe2\GitHub.copilot-chat\chat-session-resources\79355561-a4a9-49da-8214-cb3383d005fe\call_YABmeDs8Ptd2MmW9ohjuhTkL__vscode-1771404033726\content.txt"

def extract_final(path):
    data = open(path, 'r', encoding='utf-8').read()
    marker = '== Final Merged Answer =='
    if marker in data:
        idx = data.index(marker) + len(marker)
        final = data[idx:]
        # strip leading/trailing whitespace and markdown/plain artifacts
        final = final.strip('\n \r')
        return final
    # fallback: return whole file
    return data

if __name__ == '__main__':
    final = extract_final(captured)
    r = tk.Tk()
    app = OllamaGUI(r)
    # inject and process once
    app.queue.put(('merged_final', final))
    app._poll_queue()
    print('INJECTED_FINAL_PREVIEW:\n')
    print(app.final_text.get('1.0', 'end'))
    r.destroy()
