"""One-shot probe: what does deepseek-v4-pro return on a tiny judge-format prompt?

Phase 0.1's first run came back with empty `message.content` for all 12 calls,
which the parser correctly mapped to UNPARSEABLE → tie. Hypothesis: V4 Pro's
default thinking mode burned the max_tokens budget on internal reasoning,
leaving no room for the output we parse. This probe confirms the response
shape so we can fix the live script (raise max_tokens, read reasoning_content,
or switch to non-thinking mode).

Reads DEEPSEEK_API_KEY from environment. No key is ever printed.
"""

import os
from openai import OpenAI


def main() -> None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not set in process environment")

    client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
    r = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "system", "content": "You are a strict judge. Follow the format exactly."},
            {
                "role": "user",
                "content": (
                    "Pick X or Y. Output exactly:\n"
                    "PREFERENCE: <X|Y|TIE>\n"
                    "CONFIDENCE: <high|medium|low>\n"
                    "REASONING: <one sentence>\n\n"
                    "Response X: 2+2=4\nResponse Y: 2+2=5"
                ),
            },
        ],
        temperature=0,
        max_tokens=600,
    )
    msg = r.choices[0].message
    print("finish_reason:", r.choices[0].finish_reason)
    print("usage:", r.usage)
    print("content len:", len(msg.content) if msg.content else 0)
    print("content:", repr(msg.content))
    rc = getattr(msg, "reasoning_content", None)
    print("reasoning_content len:", len(rc) if rc else 0)
    if rc:
        print("reasoning_content sample (first 400 chars):")
        print(rc[:400])


if __name__ == "__main__":
    main()
