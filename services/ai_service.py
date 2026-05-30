import re

SUMMARY_PROMPT = """You are an expert educational content summarizer.

Transcript:
---
{text}
---

Provide structured output in EXACTLY this format (keep section headers):

SUMMARY:
[2-3 paragraph summary of the content]

KEY TAKEAWAYS:
1. [First key point]
2. [Second key point]
3. [Third key point]
4. [Fourth key point]
5. [Fifth key point]

STUDY NOTES:
- [Note 1]
- [Note 2]
- [Note 3]
- [Note 4]
- [Note 5]
"""

def parse_ai_response(text):
    sections = {"summary": "", "takeaways": [], "study_notes": []}
    current = None
    buf = []

    def flush():
        if current == "summary":
            sections["summary"] = "\\n".join(buf).strip()
        elif current == "takeaways":
            sections["takeaways"] = [re.sub(r"^\\d+[\\.\\)]\\s*","",l).strip() for l in buf if l.strip()]
        elif current == "study_notes":
            sections["study_notes"] = [re.sub(r"^[-•*]\\s*","",l).strip() for l in buf if l.strip()]

    for line in text.split("\\n"):
        up = line.strip().upper()
        if "SUMMARY:" in up:
            flush(); current = "summary"; buf = []
        elif "KEY TAKEAWAYS:" in up:
            flush(); current = "takeaways"; buf = []
        elif "STUDY NOTES:" in up:
            flush(); current = "study_notes"; buf = []
        else:
            if current: buf.append(line)
    flush()
    return sections

def build_ai_client(provider, api_key):
    if provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=api_key), "gpt-4o"
    elif provider == "anthropic":
        import anthropic
        return anthropic, api_key  # handled separately
    elif provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai, "gemini-1.5-flash"
    elif provider == "openrouter":
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1"), "openrouter/auto"
    elif provider == "groq":
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1"), "llama-3.3-70b-versatile"
    elif provider == "deepseek":
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url="https://api.deepseek.com"), "deepseek-chat"
    elif provider == "ollama":
        from openai import OpenAI
        return OpenAI(api_key="ollama", base_url="http://localhost:11434/v1"), "llama3.2"
    raise ValueError(f"Unknown provider: {provider}")

def call_ai(provider, api_key, model_name, prompt):
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model_name or "gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        return resp.choices[0].message.content
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model_name or "claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    elif provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name or "gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return resp.text
    elif provider in ("openrouter", "groq", "deepseek", "ollama"):
        from openai import OpenAI
        config = {
            "openrouter": ("https://openrouter.ai/api/v1", "openrouter/auto", api_key),
            "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", api_key),
            "deepseek": ("https://api.deepseek.com", "deepseek-chat", api_key),
            "ollama": ("http://localhost:11434/v1", "llama3.2", "ollama"),
        }
        base_url, default_model, key = config[provider]
        client = OpenAI(api_key=key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model_name or default_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        return resp.choices[0].message.content
    raise ValueError(f"Unknown provider: {provider}")


