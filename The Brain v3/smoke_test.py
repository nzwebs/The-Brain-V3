import sys, os, time, threading, queue
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), 'The Brain v3')))
import tkinter as tk
import gui_ollama_chat

# Fake chat to avoid network: return content showing system prompt and messages count
def fake_chat(client_url, model, messages, timeout=30, runtime_options=None):
    sys_msg = ''
    for m in messages:
        if m.get('role') == 'system':
            sys_msg = m.get('content','')
            break
    return {'content': f"[FAKE] Sys: {sys_msg[:160]}"}

# Patch
gui_ollama_chat.chat_with_ollama = fake_chat

root = tk.Tk()
root.withdraw()
app = gui_ollama_chat.OllamaGUI(root)
app.reset_defaults()

cfg = {
    'a_url': 'http://localhost:11434',
    'a_model': 'llama2',
    'a_persona': 'Analytical', 'a_age': '40', 'a_quirk': 'direct',
    'b_url': 'http://192.168.127.121:11434',
    'b_model': 'llama2',
    'b_persona': 'Playful', 'b_age': '30', 'b_quirk': 'witty',
    'topic': 'Smoke test topic', 'turns': 2, 'delay': 0.05, 'humanize': False, 'greeting': None,
    'max_chars_a': 200, 'max_chars_b': 200, 'short_turn': False, 'log': False, 'log_path': None,
    'a_runtime': {}, 'b_runtime': {},
}
q = queue.Queue()
stop_event = threading.Event()

worker = threading.Thread(target=app._run_conversation, args=(cfg, stop_event, q), daemon=True)
worker.start()

start = time.time()
while True:
    try:
        kind, text = q.get(timeout=10)
        print(kind.upper(), text)
        if kind == 'done':
            break
    except Exception:
        print('TIMEOUT waiting for queue')
        break
    if time.time() - start > 20:
        print('TEST TIMED OUT')
        break

try:
    root.destroy()
except Exception:
    pass
print('SMOKE TEST FINISHED')
