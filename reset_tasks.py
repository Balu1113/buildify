import asyncio

from mcp_client.client import MCPProjectClient


async def reset_tasks():

    mcp = MCPProjectClient()

    await mcp.connect()

    print("\nResetting unfinished tasks...\n")

    task_ids = [
        "eafd8f30",
        "1d73cefe",
        "4a8033ee",
        "4fe21bc0",
    ]

    for task_id in task_ids:

        result = await mcp.call_tool(
            "update_task",
            {
                "task_id": task_id,
                "status": "todo"
            }
        )

        print(f"{task_id} -> todo")
        print(result)

    await mcp.disconnect()


if __name__ == "__main__":
    asyncio.run(reset_tasks())