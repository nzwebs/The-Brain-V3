#!/usr/bin/env python3
"""Run the 3-phase merge protocol against real Ollama endpoints configured in gui_config.json or defaults."""
import json
import os
import sys
# ensure project root on path so multi_ollama_chat can be imported
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
from multi_ollama_chat import chat_with_ollama

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


def run(question, a_url, a_model, b_url, b_model, timeout=30):
    print('Question:', question)

    # Phase 1: independent answers
    # Use natural-language instructions (not raw JSON) so models don't echo payloads
    init_instr = (
        "Phase: initial_answer.\n"
        "Instruction: Give your best answer. Be clear, concise, and factual.\n"
        f"Question: {question}"
    )
    messages = [{'role': 'system', 'content': 'You are an assistant answering a question.'}, {'role': 'user', 'content': init_instr}]

    try:
        res_a = chat_with_ollama(a_url, a_model, messages, runtime_options=None, timeout=timeout)
    except Exception as e:
        res_a = {'content': f'[ERROR contacting A: {e}]'}
    try:
        res_b = chat_with_ollama(b_url, b_model, messages, runtime_options=None, timeout=timeout)
    except Exception as e:
        res_b = {'content': f'[ERROR contacting B: {e}]'}

    answer_a = (res_a.get('content','') or '').strip()
    answer_b = (res_b.get('content','') or '').strip()

    print('\n== Initial Answers ==')
    print('\n-- Model A --\n', answer_a)
    print('\n-- Model B --\n', answer_b)

    # Phase 2: critiques
    crit_a_text = (
        "Phase: critique.\n"
        "Instruction: Identify strengths, weaknesses, missing details, and incorrect reasoning in the other model's answer. Be objective and brief.\n"
        f"Your answer: {answer_a}\nOther answer: {answer_b}"
    )
    messages_a = [{'role':'system','content':'You are an objective critic.'}, {'role':'user','content': crit_a_text}]
    crit_b_text = (
        "Phase: critique.\n"
        "Instruction: Identify strengths, weaknesses, missing details, and incorrect reasoning in the other model's answer. Be objective and brief.\n"
        f"Your answer: {answer_b}\nOther answer: {answer_a}"
    )
    messages_b = [{'role':'system','content':'You are an objective critic.'}, {'role':'user','content': crit_b_text}]

    try:
        crit_a = chat_with_ollama(a_url, a_model, messages_a, timeout=timeout).get('content','').strip()
    except Exception as e:
        crit_a = f'[ERROR critique A: {e}]'
    try:
        crit_b = chat_with_ollama(b_url, b_model, messages_b, timeout=timeout).get('content','').strip()
    except Exception as e:
        crit_b = f'[ERROR critique B: {e}]'

    print('\n== Critiques ==')
    print('\n-- Critique A --\n', crit_a)
    print('\n-- Critique B --\n', crit_b)

    # Phase 3: final merge drafts
    merge_text = (
        "Phase: final_merge.\n"
        f"Question: {question}\n"
        f"Answer A: {answer_a}\n"
        f"Answer B: {answer_b}\n"
        f"Critique A: {crit_a}\n"
        f"Critique B: {crit_b}\n"
        "Instruction: Produce a single combined answer that integrates the best ideas from both models, fixes errors, and is clearer and more complete than either answer alone."
    )
    messages_merge = [{'role':'system','content':'You are an expert assistant that merges and synthesizes answers.'}, {'role':'user','content': merge_text}]

    try:
        draft_a = chat_with_ollama(a_url, a_model, messages_merge, timeout=timeout).get('content','').strip()
    except Exception as e:
        draft_a = f'[ERROR merge draft A: {e}]'
    try:
        draft_b = chat_with_ollama(b_url, b_model, messages_merge, timeout=timeout).get('content','').strip()
    except Exception as e:
        draft_b = f'[ERROR merge draft B: {e}]'

    print('\n== Merge Drafts ==')
    print('\n-- Draft A --\n', draft_a)
    print('\n-- Draft B --\n', draft_b)

    # Final synthesis: ask model A to synthesize drafts
    synth_text = (
        "Phase: synthesize.\n"
        "Instruction: Synthesize the two drafts into one concise final answer and briefly mention any conflicts you resolved.\n"
        f"Draft A: {draft_a}\nDraft B: {draft_b}"
    )
    messages_synth = [{'role':'system','content':'You are an expert synthesizer.'}, {'role':'user','content': synth_text}]
    try:
        final = chat_with_ollama(a_url, a_model, messages_synth, timeout=timeout).get('content','').strip()
    except Exception as e:
        final = draft_a or draft_b or f'[ERROR synth: {e}]'

    print('\n== Final Merged Answer ==\n')
    print(final)


if __name__ == '__main__':
    cfg = load_cfg()
    a_url = cfg.get('a_url') or os.getenv('AGENT_A_URL') or 'http://localhost:11434'
    b_url = cfg.get('b_url') or os.getenv('AGENT_B_URL') or 'http://192.168.127.121:11434'
    a_model = cfg.get('a_model') or os.getenv('AGENT_A_MODEL') or 'llama2'
    b_model = cfg.get('b_model') or os.getenv('AGENT_B_MODEL') or 'llama2'
    question = 'Why is the sky blue?'
    run(question, a_url, a_model, b_url, b_model)
