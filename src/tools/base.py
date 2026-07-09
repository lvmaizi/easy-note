from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class ToolParameter:
    name: str
    type: str  # "string", "integer", "boolean"
    description: str
    required: bool = True


class BaseTool(ABC):
    def __init__(self, allowed_dirs: list[str] | None = None):
        self.allowed_dirs = allowed_dirs or []

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        ...

    @abstractmethod
    def execute(self, **kwargs) -> str:
        ...

    def validate_path(self, path_str: str) -> Path:
        resolved = Path(path_str).resolve()
        # 未配置允许目录时默认拒绝（deny-by-default），避免成为全盘可读后门
        if not self.allowed_dirs:
            raise ValueError("未配置允许访问的目录")
        resolved_str = str(resolved)
        for d in self.allowed_dirs:
            allowed_str = str(Path(d).resolve())
            if resolved_str == allowed_str or resolved_str.startswith(allowed_str + os.sep):
                return resolved
        # 不回显允许目录列表，避免向 LLM 暴露沙箱边界与系统绝对路径
        raise ValueError(f"路径不在允许访问的目录内: {path_str}")

    def to_prompt_description(self) -> str:
        params_desc = "\n".join(
            f"    - {p.name} ({p.type}, {'required' if p.required else 'optional'}): {p.description}"
            for p in self.parameters
        )
        return f"""- **{self.name}**: {self.description}
  Parameters:
{params_desc}"""
