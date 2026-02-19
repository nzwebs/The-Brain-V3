import os, sys, json, threading
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
from multi_ollama_chat import chat_with_ollama
import tkinter as tk
from gui_ollama_chat import OllamaGUI

DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'gui_config.json')

def load_cfg(path=DEFAULT_CONFIG):
    cfg = {}
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
    except Exception:
        cfg = {}
    return cfg


def call_with_timeout(client_url, model, messages, timeout=30):
    result = {}
    def worker():
        try:
            res = chat_with_ollama(client_url, model, messages, runtime_options=None)
        except Exception as e:
            res = {'content': f'[ERROR contacting {client_url}: {e}]'}
        result['res'] = res
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return {'content': f'[ERROR: timeout contacting {client_url}]'}
    return result.get('res', {'content':'[ERROR: no response]'})


def run_and_inject():
    cfg = load_cfg()
    a_url = cfg.get('a_url') or os.getenv('AGENT_A_URL') or 'http://localhost:11434'
    b_url = cfg.get('b_url') or os.getenv('AGENT_B_URL') or 'http://192.168.127.121:11434'
    a_model = cfg.get('a_model') or os.getenv('AGENT_A_MODEL') or ''
    b_model = cfg.get('b_model') or os.getenv('AGENT_B_MODEL') or ''
    question = 'Why is the sky blue?'

    init_instr = (
        "Phase: initial_answer.\n"
        "Instruction: Give your best answer. Be clear, concise, and factual.\n"
        f"Question: {question}"
    )
    messages = [{'role':'system','content':'You are an assistant answering a question.'}, {'role':'user','content':init_instr}]
    res_a = call_with_timeout(a_url, a_model, messages, timeout=30)
    res_b = call_with_timeout(b_url, b_model, messages, timeout=30)
    answer_a = (res_a.get('content','') or '').strip()
    answer_b = (res_b.get('content','') or '').strip()

    crit_a_text = (
        "Phase: critique.\n"
        "Instruction: Identify strengths, weaknesses, missing details, and incorrect reasoning in the other model's answer. Be objective and brief.\n"
        f"Your answer: {answer_a}\nOther answer: {answer_b}"
    )
    crit_b_text = (
        "Phase: critique.\n"
        "Instruction: Identify strengths, weaknesses, missing details, and incorrect reasoning in the other model's answer. Be objective and brief.\n"
        f"Your answer: {answer_b}\nOther answer: {answer_a}"
    )
    crit_a = call_with_timeout(a_url, a_model, [{'role':'system','content':'You are an objective critic.'}, {'role':'user','content':crit_a_text}], timeout=30).get('content','').strip()
    crit_b = call_with_timeout(b_url, b_model, [{'role':'system','content':'You are an objective critic.'}, {'role':'user','content':crit_b_text}], timeout=30).get('content','').strip()

    merge_text = (
        "Phase: final_merge.\n"
        f"Question: {question}\n"
        f"Answer A: {answer_a}\n"
        f"Answer B: {answer_b}\n"
        f"Critique A: {crit_a}\n"
        f"Critique B: {crit_b}\n"
        "Instruction: Produce a single combined answer that integrates the best ideas from both models, fixes errors, and is clearer and more complete than either answer alone."
    )
    draft_a = call_with_timeout(a_url, a_model, [{'role':'system','content':'You are an expert assistant that merges and synthesizes answers.'}, {'role':'user','content':merge_text}], timeout=30).get('content','').strip()
    draft_b = call_with_timeout(b_url, b_model, [{'role':'system','content':'You are an expert assistant that merges and synthesizes answers.'}, {'role':'user','content':merge_text}], timeout=30).get('content','').strip()

    synth_text = (
        "Phase: synthesize.\n"
        "Instruction: Synthesize the two drafts into one concise final answer and briefly mention any conflicts you resolved.\n"
        f"Draft A: {draft_a}\nDraft B: {draft_b}"
    )
    final = call_with_timeout(a_url, a_model, [{'role':'system','content':'You are an expert synthesizer.'}, {'role':'user','content':synth_text}], timeout=30).get('content','').strip()
    if not final:
        final = draft_a or draft_b or '[ERROR: no merged output]'

    # inject into GUI preview and print preview
    r = tk.Tk()
    app = OllamaGUI(r)
    app.queue.put(('merged_final', final))
    app._poll_queue()
    print('FINAL_PREVIEW:\n')
    if app.final_text is not None:
        print(app.final_text.get('1.0','end'))
    else:
        print('[ERROR: final_text widget not initialized]')
    r.destroy()

if __name__ == '__main__':
    run_and_inject()
