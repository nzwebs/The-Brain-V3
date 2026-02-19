import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import tkinter as tk
from gui_ollama_chat import OllamaGUI

# Create hidden root
root = tk.Tk(); root.withdraw()
app = OllamaGUI(root)
# Ensure memory on
app.memory_enabled.set(True)
# Monkeypatch _call_ollama_with_timeout to avoid network calls
def fake_call(url, model, messages, runtime_options=None, timeout=20):
    # return a reply echoing the last user content if available
    last = ''
    try:
        print('\n--- fake_call invoked ---')
        print('url:', url, 'model:', model)
        print('last 6 messages:')
        for mm in messages[-6:]:
            print('  ', mm.get('role'), ':', mm.get('content'))
        for m in reversed(messages):
            if m.get('role') == 'user' and m.get('content'):
                last = m.get('content')
                break
        if not last:
            # try assistant content
            for m in reversed(messages):
                if m.get('role') == 'assistant' and m.get('content'):
                    last = m.get('content'); break
    except Exception:
        last = ''
    return {'content': f"SIMULATED_REPLY: {last}"}

app._call_ollama_with_timeout = fake_call

# start conversation
app.topic.delete(0, 'end'); app.topic.insert(0, 'Testing memory')
app.start(greeting='Start talking about testing memory')

# wait a moment for thread to process initial prompt
time.sleep(1.0)

# Inject a user fact while conversation is running
fact = 'My name is DemoUser'
app.to_worker_queue.put(fact)
print('Injected fact:', fact)

# Wait a bit to let worker process
time.sleep(2.0)

# Dump outputs from app.queue
outs = []
try:
    while True:
        msg = app.queue.get_nowait()
        outs.append(msg)
except Exception:
    pass

print('\nCaptured outputs:')
for kind, content in outs:
    print(kind, ':', content)

# Show brain.json
p = app._brain_path()
try:
    with open(p, 'r', encoding='utf-8') as f:
        print('\nbrain.json content:\n')
        print(f.read())
except Exception as e:
    print('Failed to read brain.json:', e)

# stop the conversation
app.stop()
root.destroy()
