import os
import json
import logging
from typing import List, Dict, Any

from anthropic import AsyncAnthropic

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

async def chat_with_higgsfield(messages: List[Dict[str, Any]], system_prompt: str = "") -> str:
    """
    Connects to the higgsfield-ai/skills MCP server, sends the messages to Claude,
    and allows Claude to invoke the Higgsfield tools.
    """
    # Initialize Claude Client
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment.")
    
    # We must have HIGGSFIELD_API_KEY in env for the skills bundle
    higgsfield_api_key = os.getenv("HIGGSFIELD_API_KEY")
    if not higgsfield_api_key:
        raise ValueError("HIGGSFIELD_API_KEY not found in environment.")

    anthropic = AsyncAnthropic(api_key=anthropic_api_key)

    # Prepare MCP Server execution
    # On Windows, npx.cmd is required when using subprocess directly, 
    # but stdio_client uses asyncio.create_subprocess_exec under the hood.
    command = "npx.cmd" if os.name == 'nt' else "npx"
    server_params = StdioServerParameters(
        command=command,
        args=["-y", "@higgsfield-ai/skills"],
        env=os.environ.copy() # Passes HIGGSFIELD_API_KEY automatically
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Fetch tools from Higgsfield MCP
                mcp_tools_resp = await session.list_tools()
                
                # Convert MCP tools to Anthropic tool schema
                anthropic_tools = []
                for t in mcp_tools_resp.tools:
                    anthropic_tools.append({
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema
                    })

                # Call Claude
                # We do a basic loop for tool calling
                current_messages = list(messages)
                
                while True:
                    response = await anthropic.messages.create(
                        model="claude-3-5-sonnet-latest", # or 3.7
                        max_tokens=4096,
                        system=system_prompt,
                        messages=current_messages,
                        tools=anthropic_tools
                    )

                    # Add Claude's response to the conversation
                    current_messages.append({"role": "assistant", "content": response.content})

                    # Check if Claude wants to stop
                    if response.stop_reason != "tool_use":
                        # Return the final text
                        final_text = ""
                        for block in response.content:
                            if block.type == "text":
                                final_text += block.text
                        return final_text

                    # Execute the tool calls
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input
                            logger.info(f"Claude invoking tool: {tool_name} with {tool_input}")
                            
                            try:
                                # Call the MCP server
                                result = await session.call_tool(tool_name, arguments=tool_input)
                                
                                # MCP result.content is usually a list of text blocks
                                result_text = ""
                                for c in result.content:
                                    if c.type == "text":
                                        result_text += c.text
                                
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": result_text
                                })
                            except Exception as e:
                                logger.error(f"Tool {tool_name} failed: {e}")
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": f"Error executing tool: {str(e)}",
                                    "is_error": True
                                })
                    
                    # Pass the tool results back to Claude
                    current_messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        logger.error(f"Failed to communicate with Higgsfield MCP or Claude: {e}")
        raise e
