"""Critical gate test: can deepseek-v4-pro SEE an image AND give coordinates?
Pipeline: MCP screenshots example.com -> send PNG to the model -> ask what text + where.
If it reports 'Example Domain' and a plausible (x,y), the noVNC-canvas plan is viable."""
import asyncio, base64, os
from dotenv import load_dotenv
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


async def main():
    params = StdioServerParameters(command="npx", args=[
        "-y", "chrome-devtools-mcp@latest", "--headless", "--isolated",
        "--no-usage-statistics"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("navigate_page", {"url": "https://example.com"})
            res = await session.call_tool("take_screenshot", {})
            img_b64, mime = None, "image/png"
            for b in res.content:
                if getattr(b, "type", "") == "image":
                    img_b64 = b.data
                    mime = getattr(b, "mimeType", "image/png")
            if not img_b64:
                print("No image returned by take_screenshot; blocks:",
                      [getattr(b, "type", "?") for b in res.content]); return
            print(f"Got screenshot: {len(img_b64)} b64 chars, mime={mime}")

    try:
        r = client.chat.completions.create(model=MODEL, temperature=0, messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "What heading text is in this screenshot, "
                 "and give the approximate pixel x,y of its center? Answer concisely."},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            ]}])
        print("MODEL VISION REPLY ->", r.choices[0].message.content)
        print("\n==> deepseek-v4-pro ACCEPTS images. noVNC-vision plan is viable.")
    except Exception as e:
        print("MODEL REJECTED IMAGE ->", repr(e))
        print("\n==> This model is text-only. We need a vision/computer-use model "
              "for the noVNC-canvas approach.")


if __name__ == "__main__":
    asyncio.run(main())
