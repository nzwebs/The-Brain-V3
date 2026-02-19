import os, sys, time
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
import tkinter as tk
from gui_ollama_chat import OllamaGUI

if __name__ == '__main__':
    r = tk.Tk()
    app = OllamaGUI(r)
    # start live merge (will create progress Toplevel)
    app._on_run_live_merge()
    # wait for merged_final in queue (timeout 120s)
    start = time.time()
    final = None
    try:
        while time.time() - start < 120:
            # process tkinter events so Toplevel and updates work
            try:
                r.update()
            except Exception:
                pass
            try:
                kind, text = app.queue.get_nowait()
                if kind == 'merged_final':
                    final = text
                    break
            except Exception:
                # no item yet
                time.sleep(0.1)
                continue
    except KeyboardInterrupt:
        pass
    if final is None:
        print('ERROR: no merged_final received in 120s')
    else:
        print('MERGED_FINAL:\n')
        print(final)
    try:
        r.destroy()
    except Exception:
        pass
