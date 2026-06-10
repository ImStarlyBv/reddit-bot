"""Verify the DeepSeek key works AND that tool/function-calling works (the agent depends on it)."""
import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))

# 1) plain ping
r = client.chat.completions.create(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    messages=[{"role": "user", "content": "Reply with exactly: PONG"}],
    temperature=0,
)
print("1) chat ping  ->", repr(r.choices[0].message.content))

# 2) tool calling
tools = [{"type": "function", "function": {
    "name": "navigate_page",
    "description": "Open a URL in the browser.",
    "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                   "required": ["url"]},
}}]
r2 = client.chat.completions.create(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    messages=[{"role": "user", "content": "Open reddit.com/r/all"}],
    tools=tools, tool_choice="auto", temperature=0,
)
tc = r2.choices[0].message.tool_calls
if tc:
    print("2) tool call  ->", tc[0].function.name, tc[0].function.arguments)
else:
    print("2) tool call  -> NONE (model answered with text):", r2.choices[0].message.content)
print("\nDeepSeek side OK.")
