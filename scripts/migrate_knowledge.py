"""一次性迁移脚本：把 classics.json / rules.json 拆成独立 .md 文件。

用法：
    python3 scripts/migrate_knowledge.py

输出：
    knowledge/classics/<source_id>.md   (81 篇)
    knowledge/rules/<rule_id>.md        (61 条)

每个文件带 YAML frontmatter（供 ripgrep 快速过滤），正文是人可读的 Markdown。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSICS_JSON = ROOT / "knowledge" / "classics.json"
RULES_JSON = ROOT / "knowledge" / "rules.json"
CLASSICS_DIR = ROOT / "knowledge" / "classics"
RULES_DIR = ROOT / "knowledge" / "rules"


def migrate_classics():
    data = json.loads(CLASSICS_JSON.read_text("utf-8"))
    CLASSICS_DIR.mkdir(parents=True, exist_ok=True)
    for item in data:
        sid = item["source_id"]
        tags = ", ".join(item.get("topic_tags", []))
        md = f"""---
id: {sid}
system: {item.get('system', '')}
school: {item.get('school', '')}
title: "{item.get('title', '')}"
author: {item.get('author', '')}
era: {item.get('era', '')}
tags: [{tags}]
---

# {item.get('title', sid)}

> {item.get('quote', '')}

{item.get('summary', '')}

**适用场景**: {item.get('applies_when', '通用')}
"""
        (CLASSICS_DIR / f"{sid}.md").write_text(md.strip() + "\n", "utf-8")
    print(f"✓ 迁移 {len(data)} 篇典籍 → {CLASSICS_DIR}")


def migrate_rules():
    data = json.loads(RULES_JSON.read_text("utf-8"))
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    for item in data:
        rid = item["rule_id"]
        trigger = json.dumps(item.get("trigger", {}), ensure_ascii=False)
        examples = ", ".join(item.get("manifest_examples", []))
        sources = ", ".join(item.get("source_ids", []))
        md = f"""---
id: {rid}
system: {item.get('system', '')}
school: {item.get('school', '')}
category: {item.get('category', '')}
name: "{item.get('name', '')}"
confidence: {item.get('confidence_prior', 'medium')}
sources: [{sources}]
---

# {item.get('name', rid)}

**触发条件**: {trigger}

**结论**: {item.get('conclusion', '')}

**表现示例**: {examples}

**备注**: {item.get('notes', '')}
"""
        (RULES_DIR / f"{rid}.md").write_text(md.strip() + "\n", "utf-8")
    print(f"✓ 迁移 {len(data)} 条规则 → {RULES_DIR}")


if __name__ == "__main__":
    migrate_classics()
    migrate_rules()
    print("Done.")
