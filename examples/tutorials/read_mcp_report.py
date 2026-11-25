"""Read one teaching report as a CareerLens MCP tool and as a resource."""

import argparse
import asyncio
import json
from getpass import getpass

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client


async def read_report(url: str, user_id: str, report_id: str, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    async with create_mcp_http_client(headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            incoming, outgoing = streams[:2]
            async with ClientSession(incoming, outgoing) as client:
                await client.initialize()
                response = await client.call_tool(
                    "get_career_report", {"user_id": user_id, "report_id": report_id}
                )
                if response.is_error:
                    raise RuntimeError(response.content[0].text)
                report = response.structured_content or json.loads(response.content[0].text)
                resource = await client.read_resource(f"report://{user_id}/{report_id}")
                resource_report = json.loads(resource.contents[0].text)
    if report != resource_report or report["report_id"] != report_id:
        raise RuntimeError("The tool and resource did not return the same report.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id")
    parser.add_argument("report_id")
    args = parser.parse_args()
    token = getpass("CareerLens read token: ").strip()
    report = asyncio.run(
        read_report("http://localhost:8001/mcp", args.user_id, args.report_id, token)
    )
    print("report_id:", report["report_id"])
    print("version:", report["version"])
    print(report["markdown"].splitlines()[0])


if __name__ == "__main__":
    main()
