import asyncio

from mcp_client.client import MCPProjectClient


async def main():

    client = MCPProjectClient()

    await client.connect()

    print("\nMCP connection successful!")

    print("\nAvailable tools:")

    tools = await client.list_tools()

    for tool in tools:
        print(f"✓ {tool.name}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())