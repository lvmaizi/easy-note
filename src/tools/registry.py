from src.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def execute(self, name: str, params: dict) -> str:
        tool = self._tools.get(name)
        if not tool:
            available = ", ".join(self._tools.keys())
            return f"Error: Unknown tool '{name}'. Available tools: {available}"
        try:
            return tool.execute(**params)
        except TypeError as e:
            expected = [p.name for p in tool.parameters]
            return (
                f"Error: Invalid parameters for tool '{name}': {e}\n"
                f"Expected parameters: {expected}\n"
                f"Received: {list(params.keys())}"
            )
        except Exception as e:
            return f"Error executing tool '{name}': {e}"

    def build_tools_prompt(self) -> str:
        descriptions = [t.to_prompt_description() for t in self._tools.values()]
        return "\n".join(descriptions)
