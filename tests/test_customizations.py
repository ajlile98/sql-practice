import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration


def test_repository_skill_and_tasks_contract():
    file_path = ROOT / ".github/skills/sql-practice/SKILL.md"
    frontmatter = file_path.read_text().split("---", 2)[1]
    skill = yaml.safe_load(frontmatter)
    assert skill["name"] == file_path.parent.name
    assert "SQL practice" in skill["description"]
    assert skill.get("user-invocable", True)
    tasks = json.loads((ROOT / ".vscode/tasks.json").read_text())
    assert all(task["type"] == "process" and task["command"] == "uv" for task in tasks["tasks"])
    workflow = yaml.load((ROOT / ".github/workflows/test.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push", "pull_request"}
