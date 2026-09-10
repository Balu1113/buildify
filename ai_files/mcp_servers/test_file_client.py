import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


server_params = StdioServerParameters(
    command="python",
    args=["mcp_servers/file_server.py"],
)


async def main():

    async with stdio_client(server_params) as (read, write):

        async with ClientSession(read, write) as session:

            await session.initialize()

            print("\n" + "=" * 60)
            print("FILE MCP SERVER TEST")
            print("=" * 60)

            # ==================================================
            # DISCOVER TOOLS
            # ==================================================

            tools_result = await session.list_tools()

            print("\nAvailable tools:")

            for tool in tools_result.tools:
                print(f"✓ {tool.name}")

            # ==================================================
            # LIST PROJECT FILES
            # ==================================================

            print("\n" + "-" * 60)
            print("PROJECT FILES")
            print("-" * 60)

            result = await session.call_tool(
                "list_files",
                arguments={
                    "directory": "."
                }
            )

            for content in result.content:

                if hasattr(content, "text"):

                    data = json.loads(
                        content.text
                    )

                    print(
                        json.dumps(
                            data,
                            indent=2
                        )
                    )

            # ==================================================
            # CREATE TEST FILE
            # ==================================================

            print("\n" + "-" * 60)
            print("CREATING TEST FILE")
            print("-" * 60)

            result = await session.call_tool(
                "create_file",
                arguments={
                    "file_path": "test_agent_file.txt",
                    "content": (
                        "Created by the File MCP Server."
                    )
                }
            )

            for content in result.content:

                if hasattr(content, "text"):

                    print(content.text)

            # ==================================================
            # READ TEST FILE
            # ==================================================

            print("\n" + "-" * 60)
            print("READING TEST FILE")
            print("-" * 60)

            result = await session.call_tool(
                "read_file",
                arguments={
                    "file_path": "test_agent_file.txt"
                }
            )

            for content in result.content:

                if hasattr(content, "text"):

                    data = json.loads(
                        content.text
                    )

                    print(
                        json.dumps(
                            data,
                            indent=2
                        )
                    )

            print("\n" + "=" * 60)
            print("FILE MCP TEST COMPLETED")
            print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())