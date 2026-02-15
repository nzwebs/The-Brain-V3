#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_ollama_chat.py - CLI for running a conversation between two Ollama agents.
"""

import argparse
import os
import sys
import time
import threading
import signal
from datetime import datetime

try:
    import msvcrt
except Exception:
    msvcrt = None

try:
    import ollama
except Exception:
    print(
        "Failed to import 'ollama' package. Install it with 'pip install ollama'",
        file=sys.stderr,
    )
    raise


# Configuration with environment variable overrides
AGENT_A_URL = os.getenv("AGENT_A_URL", "http://localhost:11434")
AGENT_A_MODEL = os.getenv("AGENT_A_MODEL", "llama2")
AGENT_A_NAME = os.getenv("AGENT_A_NAME", "Agent_A")

AGENT_B_URL = os.getenv("AGENT_B_URL", "http://192.168.127.121:11434")
AGENT_B_MODEL = os.getenv("AGENT_B_MODEL", "llama2")
AGENT_B_NAME = os.getenv("AGENT_B_NAME", "Agent_B")


def chat_with_ollama(client_url, model, messages, timeout=30, runtime_options=None):
    """Sends messages to an Ollama server and returns a dict with 'content'."""
    client = ollama.Client(host=client_url)
    try:
        # Try to pass runtime options (temperature, max_tokens, top_p, stop, stream, etc.)
        if runtime_options and isinstance(runtime_options, dict):
            try:
                response = client.chat(model=model, messages=messages, **runtime_options)
            except TypeError:
                response = client.chat(model=model, messages=messages)
        else:
            response = client.chat(model=model, messages=messages)
    except Exception as e:
        return {"content": f"[ERROR calling {client_url}: {e}]"}

    def extract_from_text(text: str) -> str:
        import re

        if not text:
            return ""
        m2 = re.search(r"Message\([^)]*content=(?:\'|\")(.*?)(?:\'|\")(?:,|\))", text, re.S)
        if m2:
            return m2.group(1)
        m = re.search(r"content=(?:\'|\")(?P<c>.*?)(?:\'|\")", text, re.S)
        if m:
            return m.group("c")
        return text

    def clean_content(text: str) -> str:
        import re

        if not text:
            return ""
        s = str(text)
        s = extract_from_text(s)
        s = re.sub(r"\bmodel=[^\s,]+", "", s)
        s = re.sub(r"\bcreated_at=[^\s,]+", "", s)
        s = re.sub(r"\bdone=[^\s,]+", "", s)
        s = re.sub(r"\btotal_duration=[^\s,]+", "", s)
        s = re.sub(r"message=Message\([^)]*\)", "", s)
        s = re.sub(r"(?m)^(Agent_[AB]:\s*)+", "", s)
        s = re.sub(r"Agent_[AB]:", "", s)
        s = re.sub(r"\n{2,}", "\n", s)
        lines = [ln.strip() for ln in s.splitlines()]
        s = " ".join([ln for ln in lines if ln != ""])
        s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        s = s.replace("—", "-").replace("–", "-")
        s = re.sub(r"\.{2,}", "...", s)
        s = re.sub(r"([!?\.]){2,}", r"\1", s)
        s = re.sub(r"([\.\!\?])([^\s\.,!\?])", r"\1 \2", s)
        s = re.sub(r"[ \t]{2,}", " ", s)
        try:
            from autocorrect import Speller

            sp = Speller(lang="en")

            def _spell_token(tok: str) -> str:
                m = re.match(r"^(\W*)([\w'-]+)(\W*)$", tok)
                if m:
                    pre, word, post = m.groups()
                    if re.search(r"[=\"'`/\\:.@#]", (pre or "") + (post or "")):
                        return pre + word + (post or "")
                    if re.fullmatch(r"[A-Za-z'-]{2,}", word):
                        corrected = sp(word)
                        return pre + corrected + (post or "")
                    return pre + word + (post or "")
                return tok

            tokens = s.split(" ")
            s = " ".join(_spell_token(t) for t in tokens)
        except Exception:
            pass
        return s.strip()

    if isinstance(response, dict):
        if "message" in response:
            msg = response["message"]
            if isinstance(msg, dict):
                content = msg.get("content") or msg.get("text") or str(msg)
                return {"content": clean_content(extract_from_text(content))}
            return {"content": clean_content(extract_from_text(str(msg)))}
        if "content" in response:
            return {"content": clean_content(extract_from_text(response["content"]))}
    return {"content": clean_content(extract_from_text(str(response)))}


def run_conversation(
    topic,
    turns=5,
    delay=1.0,
    log_path=None,
    humanize=False,
    greeting=None,
    persona_a=None,
    persona_b=None,
    max_chars=None,
    short_turn=False,
    model_a=None,
    model_b=None,
):
    """Orchestrates a conversation between two agents. Each turn both agents reply.

    Args:
        topic (str): Topic to discuss.
        turns (int): Number of rounds (each round: B -> A).
        delay (float): Seconds to sleep between turns.
    """
    base_sys_a = f"You are {AGENT_A_NAME}. You are discussing the topic: '{topic}' with {AGENT_B_NAME}. Be concise and engaging."
    base_sys_b = f"You are {AGENT_B_NAME}. You are discussing the topic: '{topic}' with {AGENT_A_NAME}. Be concise and engaging."

    if persona_a:
        base_sys_a += f" Persona: {persona_a}"
    if persona_b:
        base_sys_b += f" Persona: {persona_b}"

    if humanize:
        human_instruct = (
            "Speak like a friendly human: keep replies short, natural, use contractions and greetings, "
            "and occasionally use small talk. Follow the example exchange: \n"
            "Agent_B: 'Hello, how are you?'\nAgent_A: 'I'm very well, thank you.'"
        )
        base_sys_a = base_sys_a + " " + human_instruct
        base_sys_b = base_sys_b + " " + human_instruct

    messages_a = [{"role": "system", "content": base_sys_a}]
    messages_b = [{"role": "system", "content": base_sys_b}]

    print(f"--- Starting conversation on: '{topic}' ---")
    print("Type 'stop' and press Enter at any time to end the conversation.")

    # Agent B starts the conversation
    if humanize:
        initial_prompt = greeting or "Hello, how are you?"
    else:
        initial_prompt = f"Let's discuss {topic}. I think..."

    print(f"{AGENT_B_NAME} (initial thought): {initial_prompt}")
    messages_b.append({"role": "user", "content": initial_prompt})

    stop_event = threading.Event()

    # Open log file once so we can close it cleanly on shutdown
    log_file = None
    if log_path:
        try:
            log_file = open(log_path, "a", encoding="utf-8")
        except Exception:
            log_file = None

    # Input listener: use msvcrt on Windows for non-blocking console reads
    def input_listener():
        try:
            if msvcrt:
                buf = ""
                while not stop_event.is_set():
                    if msvcrt.kbhit():
                        ch = msvcrt.getwche()
                        if ch in ("\r", "\n"):
                            line = buf
                            buf = ""
                            if line.strip().lower() in ("stop", "q", "quit"):
                                stop_event.set()
                                break
                        else:
                            buf += ch
                    else:
                        time.sleep(0.1)
            else:
                while not stop_event.is_set():
                    line = sys.stdin.readline()
                    if not line:
                        break
                    if line.strip().lower() in ("stop", "q", "quit"):
                        stop_event.set()
                        break
        except Exception:
            stop_event.set()

    listener = threading.Thread(target=input_listener, daemon=True)
    listener.start()

    transcript = []

    def log(message):
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
        transcript.append(entry)
        print(entry)
        if log_file:
            try:
                log_file.write(entry + "\n")
                log_file.flush()
            except Exception:
                pass

    # Signal handler for immediate Ctrl+C handling
    def _sigint(signum, frame):
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _sigint)
    except Exception:
        pass

    def truncate_text(text: str) -> str:
        import re

        if not text:
            return ""
        # If short_turn, return first sentence-like chunk
        if short_turn:
            m = re.search(r"(.+?[.!?])(\s|$)", text.strip(), re.S)
            if m:
                return m.group(1).strip()
        if max_chars and isinstance(max_chars, int) and max_chars > 0:
            return text.strip()[:max_chars]
        return text.strip()

    # quick topic similarity check (keyword overlap)
    def topic_similarity(text: str, topic: str) -> float:
        try:
            import re

            if not text or not topic:
                return 0.0
            toks = re.findall(r"\w+", text.lower())
            tset = set(re.findall(r"\w+", topic.lower()))
            if not tset:
                return 0.0
            common = sum(1 for t in toks if t in tset)
            return common / max(1, len(toks))
        except Exception:
            return 0.0

    # choose models (CLI overrides function args; fall back to globals)
    m_a = model_a or AGENT_A_MODEL
    m_b = model_b or AGENT_B_MODEL

    try:
        for i in range(turns):
            if stop_event.is_set():
                break

            log(f"\n--- Turn {i + 1} ---")

            # Agent B responds
            response_b = chat_with_ollama(AGENT_B_URL, m_b, messages_b)
            content_b = truncate_text(response_b.get("content", ""))
            # Enforce strict on-topic replies
            for _ in range(2):
                if stop_event.is_set():
                    break
                sim = topic_similarity(content_b, topic)
                if sim < 0.5:  # much stricter threshold
                    messages_b.append(
                        {
                            "role": "user",
                            "content": f'IMPORTANT: Stay strictly on topic: "{topic}". Give a short, focused answer only about this topic.',
                        }
                    )
                    response_b2 = chat_with_ollama(AGENT_B_URL, m_b, messages_b)
                    content_b2 = truncate_text(response_b2.get("content", ""))
                    if topic_similarity(content_b2, topic) > sim:
                        content_b = content_b2
                    if messages_b and messages_b[-1].get("role") == "user" and "IMPORTANT: Stay strictly on topic" in messages_b[-1].get("content", ""):
                        messages_b.pop()
                else:
                    break
            log(f"{AGENT_B_NAME}: {content_b}")
            messages_b.append({"role": "assistant", "content": content_b})
            messages_a.append({"role": "user", "content": content_b})

            if stop_event.is_set():
                break

            # Agent A responds
            response_a = chat_with_ollama(AGENT_A_URL, m_a, messages_a)
            content_a = truncate_text(response_a.get("content", ""))
            for _ in range(2):
                if stop_event.is_set():
                    break
                sim = topic_similarity(content_a, topic)
                if sim < 0.5:
                    messages_a.append(
                        {
                            "role": "user",
                            "content": f'IMPORTANT: Stay strictly on topic: "{topic}". Give a short, focused answer only about this topic.',
                        }
                    )
                    response_a2 = chat_with_ollama(AGENT_A_URL, m_a, messages_a)
                    content_a2 = truncate_text(response_a2.get("content", ""))
                    if topic_similarity(content_a2, topic) > sim:
                        content_a = content_a2
                    if messages_a and messages_a[-1].get("role") == "user" and "IMPORTANT: Stay strictly on topic" in messages_a[-1].get("content", ""):
                        messages_a.pop()
                else:
                    break
            log(f"{AGENT_A_NAME}: {content_a}")
            messages_a.append({"role": "assistant", "content": content_a})
            messages_b.append({"role": "user", "content": content_a})

            # Make stopping more responsive: sleep in small increments
            slept = 0.0
            while slept < delay:
                if stop_event.is_set():
                    break
                time.sleep(min(0.05, delay - slept))
                slept += 0.05

    except KeyboardInterrupt:
        stop_event.set()
        print("\n--- Interrupted by user (Ctrl+C). Stopping conversation... ---")
    finally:
        stop_event.set()
        # give the listener a moment to exit, then join
        try:
            listener.join(timeout=1.0)
        except Exception:
            pass
        # Close log file if we opened one
        if log_file:
            try:
                log_file.close()
            except Exception:
                pass

        print("\n--- Conversation finished ---")
        if log_path:
            print(f"Transcript saved to: {log_path}")


def parse_args():
    p = argparse.ArgumentParser(description="Run a multi-OLLAMA agent conversation")
    p.add_argument("--topic", "-t", default="the benefits of remote work")
    p.add_argument("--turns", type=int, default=4)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--log", type=str, default=None, help="Optional path to append transcript")
    p.add_argument(
        "--humanize",
        action="store_true",
        help="Make agents reply in a short, human-like conversational style",
    )
    p.add_argument(
        "--greeting",
        type=str,
        default=None,
        help="Optional greeting/initial prompt when using --humanize",
    )
    p.add_argument(
        "--persona-a",
        type=str,
        default=None,
        help="Optional persona string for Agent A",
    )
    p.add_argument(
        "--persona-b",
        type=str,
        default=None,
        help="Optional persona string for Agent B",
    )
    p.add_argument("--persona-a-age", type=str, default=None, help="Optional age for Agent A")
    p.add_argument(
        "--persona-a-background",
        type=str,
        default=None,
        help="Optional background for Agent A",
    )
    p.add_argument(
        "--persona-a-quirk",
        type=str,
        default=None,
        help="Optional speaking quirk for Agent A",
    )
    p.add_argument("--persona-b-age", type=str, default=None, help="Optional age for Agent B")
    p.add_argument(
        "--persona-b-background",
        type=str,
        default=None,
        help="Optional background for Agent B",
    )
    p.add_argument(
        "--persona-b-quirk",
        type=str,
        default=None,
        help="Optional speaking quirk for Agent B",
    )
    p.add_argument(
        "--model-a",
        type=str,
        default=None,
        help="Optional model name for Agent A (overrides env AGENT_A_MODEL)",
    )
    p.add_argument(
        "--model-b",
        type=str,
        default=None,
        help="Optional model name for Agent B (overrides env AGENT_B_MODEL)",
    )
    p.add_argument("--max-chars", type=int, default=None, help="Optional max characters per reply")
    p.add_argument(
        "--short-turn",
        action="store_true",
        help="Force replies to a single short sentence",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Build richer persona strings from individual fields if provided
    def build_persona(base, age, background, quirk):
        parts = []
        if base:
            parts.append(base)
        if age:
            parts.append(f"Age: {age}")
        if background:
            parts.append(f"Background: {background}")
        if quirk:
            parts.append(f"Quirk: {quirk}")
        return " | ".join(parts) if parts else None

    persona_a_final = build_persona(
        args.persona_a or os.getenv("AGENT_A_PERSONA"),
        args.persona_a_age,
        args.persona_a_background,
        args.persona_a_quirk,
    )
    persona_b_final = build_persona(
        args.persona_b or os.getenv("AGENT_B_PERSONA"),
        args.persona_b_age,
        args.persona_b_background,
        args.persona_b_quirk,
    )

    model_a_final = args.model_a or os.getenv("AGENT_A_MODEL") or AGENT_A_MODEL
    model_b_final = args.model_b or os.getenv("AGENT_B_MODEL") or AGENT_B_MODEL

    run_conversation(
        args.topic,
        turns=args.turns,
        delay=args.delay,
        log_path=args.log,
        humanize=args.humanize,
        greeting=args.greeting,
        persona_a=persona_a_final,
        persona_b=persona_b_final,
        max_chars=args.max_chars,
        short_turn=args.short_turn,
        model_a=model_a_final,
        model_b=model_b_final,
    )
