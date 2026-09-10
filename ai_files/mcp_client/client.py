import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPProjectClient:

    def __init__(
        self,
        server_script="mcp_servers/project_server.py"
    ):

        self.server_params = StdioServerParameters(
            command="python",
            args=[server_script],
        )

        self.stdio = None
        self.session = None

    async def connect(self):

        self.stdio = stdio_client(
            self.server_params
        )

        self.read, self.write = await self.stdio.__aenter__()

        self.session = ClientSession(
            self.read,
            self.write
        )

        await self.session.__aenter__()

        await self.session.initialize()

    async def disconnect(self):

        if self.session:

            await self.session.__aexit__(
                None,
                None,
                None
            )

            self.session = None

        if self.stdio:

            await self.stdio.__aexit__(
                None,
                None,
                None
            )

            self.stdio = None

    async def list_tools(self):

        result = await self.session.list_tools()

        return result.tools

    async def call_tool(
        self,
        tool_name,
        arguments
    ):

        result = await self.session.call_tool(
            tool_name,
            arguments=arguments
        )

        results = []

        for content in result.content:

            if not hasattr(content, "text"):
                continue

            text = content.text

            try:

                parsed = json.loads(text)

                results.append(parsed)

            except json.JSONDecodeError:

                results.append(text)

        return results