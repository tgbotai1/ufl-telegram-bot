import aiohttp
import config


async def ask_agent(messages: list[dict]) -> tuple[str, int]:
    """
    Send messages to agent-ufl and return (response_text, tokens_used).
    messages: list of {"role": "user"|"assistant", "content": str}
    """
    payload = {
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {config.AGENT_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{config.AGENT_API_URL}/api/v1/chat/completions"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            resp.raise_for_status()
            data = await resp.json()

    content = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return content, tokens
