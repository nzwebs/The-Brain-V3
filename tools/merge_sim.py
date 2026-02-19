#!/usr/bin/env python3
"""Simple local simulation of the 3‑phase two-model merge protocol.
This fakes Model A and Model B responses for demonstration only.
"""

def fake_model(name, payload):
    phase = payload.get('phase')
    if phase == 'initial_answer':
        if name == 'A':
            return (
                "Model A: The sky is blue due to Rayleigh scattering. Shorter wavelengths (blue) scatter more in the atmosphere, "
                "so blue light is redirected across the sky and appears dominant."
            )
        else:
            return (
                "Model B: Sunlight is scattered by air molecules; blue wavelengths scatter more than red, "
                "making the sky look blue. At sunrise/sunset, the longer path through atmosphere makes the sky redder."
            )
    if phase == 'critique':
        your = payload.get('your_answer','')
        other = payload.get('other_answer','')
        if name == 'A':
            return "Critique A: Good explanation; add the term 'Rayleigh scattering' and mention wavelength dependence explicitly."
        else:
            return "Critique B: Concise and correct; could expand on why scattering favors shorter wavelengths and note sunsets."
    if phase == 'final_merge':
        # produce a short merge draft (models might do different stylistic merges)
        if name == 'A':
            return (
                "Draft A (merge): Rayleigh scattering causes shorter (blue) wavelengths of sunlight to scatter more than longer (red) wavelengths, "
                "so the sky appears blue during the day. At sunrise and sunset the light passes through more atmosphere, so reds dominate."
            )
        else:
            return (
                "Draft B (merge): Air molecules scatter sunlight; because blue light is scattered more strongly (Rayleigh scattering), "
                "the sky looks blue. Longer paths at dawn/dusk favor redder colors."
            )
    return ''


def synthesize(draft_a, draft_b):
    # Simple deterministic synth: collect unique sentences in order and join.
    seen = set(); out = []
    for draft in (draft_a, draft_b):
        for s in [s.strip() for s in draft.split('.') if s.strip()]:
            if s not in seen:
                seen.add(s); out.append(s)
    return '. '.join(out) + '.'


def main():
    question = "Why is the sky blue?"
    print("QUESTION:\n", question)

    # Phase 1: Independent answers
    a = fake_model('A', {'phase':'initial_answer', 'question':question})
    b = fake_model('B', {'phase':'initial_answer', 'question':question})
    print('\n== Initial Answers ==')
    print('\n-- Model A --\n', a)
    print('\n-- Model B --\n', b)

    # Phase 2: Cross-examination (critiques)
    ca = fake_model('A', {'phase':'critique', 'your_answer':a, 'other_answer':b})
    cb = fake_model('B', {'phase':'critique', 'your_answer':b, 'other_answer':a})
    print('\n== Critiques ==')
    print('\n-- Critique A --\n', ca)
    print('\n-- Critique B --\n', cb)

    # Phase 3: Final merge drafts
    da = fake_model('A', {'phase':'final_merge', 'answer_A':a, 'answer_B':b, 'critique_A':ca, 'critique_B':cb})
    db = fake_model('B', {'phase':'final_merge', 'answer_A':a, 'answer_B':b, 'critique_A':ca, 'critique_B':cb})
    print('\n== Merge Drafts ==')
    print('\n-- Draft A --\n', da)
    print('\n-- Draft B --\n', db)

    # Synthesize final answer
    final = synthesize(da, db)
    print('\n== Final Merged Answer ==\n')
    print(final)

if __name__ == '__main__':
    main()
