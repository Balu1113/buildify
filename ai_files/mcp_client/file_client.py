from pathlib import Path

from mcp_client.client import MCPProjectClient


class MCPFileClient(MCPProjectClient):

    def __init__(self):

        server_path = (
            Path(__file__).resolve().parent.parent
            / "mcp_servers"
            / "file_server.py"
        )

        super().__init__(
            str(server_path)
        )

    async def list_files(
        self,
        directory="."
    ):

        return await self.call_tool(
            "list_files",
            {
                "directory": directory
            }
        )

    async def read_file(
        self,
        file_path
    ):

        return await self.call_tool(
            "read_file",
            {
                "file_path": file_path
            }
        )

    async def create_file(
        self,
        file_path,
        content
    ):

        return await self.call_tool(
            "create_file",
            {
                "file_path": file_path,
                "content": content
            }
        )

    async def update_file(
        self,
        file_path,
        content
    ):

        return await self.call_tool(
            "update_file",
            {
                "file_path": file_path,
                "content": content
            }
        )