import json
import os
from datetime import datetime

BRAIN_PATH = os.path.join(os.path.dirname(__file__), 'brain.json')

def load_brain():
    if os.path.exists(BRAIN_PATH):
        with open(BRAIN_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'history': []}

def save_brain(brain):
    with open(BRAIN_PATH, 'w', encoding='utf-8') as f:
        json.dump(brain, f, indent=2)

def add_to_brain(agent, message, role):
    brain = load_brain()
    brain['history'].append({
        'timestamp': datetime.now().isoformat(),
        'agent': agent,
        'role': role,
        'message': message
    })
    # Keep only the last 200 messages for speed
    brain['history'] = brain['history'][-200:]
    save_brain(brain)

def get_brain_summary_prompt():
    brain = load_brain()
    # Use only the last 20 exchanges for summary
    history = brain['history'][-40:]
    lines = [f"{h['agent']} ({h['role']}): {h['message']}" for h in history]
    summary_prompt = (
        "Summarize the main arguments and conclusions from our conversation so far. "
        "Be concise and cover both perspectives.\n"
        + '\n'.join(lines)
    )
    return summary_prompt

# Example usage:
if __name__ == '__main__':
    add_to_brain('Ava', 'Let’s discuss the future of AI.', 'user')
    add_to_brain('Orion', 'AI will transform many industries.', 'assistant')
    print(get_brain_summary_prompt())
