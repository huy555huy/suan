"""工具注册表 — 单 agent 可调用的全部工具。

每个工具 = (json_schema, async execute_fn)。
agent.py 的 ReAct loop 调用这里的 dispatch()。
"""
from __future__ import annotations
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.schemas import BirthInfo, Charts
from core.intake import IntakeError, assert_chart_ready

logger = logging.getLogger("suan.tools")

ROOT = Path(__file__).resolve().parent.parent
CLASSICS_DIR = ROOT / "knowledge" / "classics"
RULES_DIR = ROOT / "knowledge" / "rules"
SKILLS_DIR = ROOT / "skills"
GOLDEN_CASES_PATH = ROOT / "data" / "pro_golden_cases.json"


# ── 工具 JSON Schema（给 LLM function-calling 用）───────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "加载一个命理技能的完整方法论到上下文。技能会教你怎么用其它工具做这个系统的解读。可用技能: bazi, ziwei, yijing, fengshui, astrology, tarot, numerology, cross_synthesis, safety_psych",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名称",
                        "enum": ["bazi", "ziwei", "yijing", "fengshui", "astrology", "tarot", "numerology", "cross_synthesis", "safety_psych"],
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_chart",
            "description": "计算命理盘面。返回完整 JSON 结构（四柱、宫位、行星等）。必须先算盘才能解读。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "description": "要算的盘面类型",
                        "enum": ["bazi", "ziwei", "hexagram", "fengshui", "natal_astro", "transit_astro", "tarot", "numerology"],
                    }
                },
                "required": ["chart_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "把用户明确补充的事实写入本轮计算档案。只可写用户明示字段，不能猜测或补默认值。常用于 ask_user 后补入性别、风水朝向/入住年、起卦输入、塔罗抽牌结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "gender": {
                        "type": "string",
                        "enum": ["male", "female", "other"],
                        "description": "用户明确补充的排盘性别。",
                    },
                    "facing_degree": {
                        "type": "number",
                        "description": "房屋朝向罗盘度数，正北=0，顺时针 0-360。",
                    },
                    "move_in_year": {
                        "type": "integer",
                        "description": "入住公历年。",
                    },
                    "built_year": {
                        "type": "integer",
                        "description": "建成公历年。",
                    },
                    "hexagram_numbers": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "梅花易数用户给出的 2 或 3 个数字。",
                    },
                    "coin_results": {
                        "type": "array",
                        "description": "六次铜钱结果；每次 3 枚，1=正，0=反。",
                        "items": {
                            "type": "array",
                            "items": {"type": "integer", "enum": [0, 1]},
                        },
                    },
                    "divination_time": {
                        "type": "string",
                        "description": "明确起卦时间，ISO 格式，如 2026-05-19T12:00:00。",
                    },
                    "tarot_spread": {
                        "type": "string",
                        "description": "用户指定的塔罗牌阵。",
                    },
                    "tarot_card_indexes": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "用户抽到的塔罗牌序号。",
                    },
                    "tarot_reversed_flags": {
                        "type": "array",
                        "items": {"type": "boolean"},
                        "description": "每张塔罗牌是否逆位。",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_classics",
            "description": "在命理典籍库中搜索关键词/正则。返回匹配的文件名和匹配行。用于找引证依据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（支持正则，如 '驿马|出行|调动'）",
                    },
                    "system": {
                        "type": "string",
                        "description": "限定体系（可选）",
                        "enum": ["bazi", "ziwei", "yijing", "fengshui", "astrology", "tarot", "numerology"],
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_classic",
            "description": "读取一篇典籍的全文。先用 grep_classics 找到 id，再用此工具读全文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "典籍 source_id（即文件名去掉 .md）",
                    }
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_rules",
            "description": "在命理规则库中搜索关键词/正则。返回匹配的规则文件名和匹配行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（支持正则）",
                    },
                    "system": {
                        "type": "string",
                        "description": "限定体系（可选）",
                        "enum": ["bazi", "ziwei", "yijing", "fengshui", "astrology", "tarot", "numerology"],
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_rule",
            "description": "读取一条规则的全文。先用 grep_rules 找到 id，再用此工具读全文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "规则 rule_id（即文件名去掉 .md）",
                    }
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_golden_cases",
            "description": "读取同体系专业黄金案例。用于在输出核心判断前参考人工盘例的事实锚点和解释锚点；案例不能替代当前盘面校验。",
            "parameters": {
                "type": "object",
                "properties": {
                    "system": {
                        "type": "string",
                        "description": "要读取的命理体系。",
                        "enum": ["bazi", "ziwei", "yijing", "fengshui"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回多少个案例，默认 3。",
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["system"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_chart_ref",
            "description": "校验你引用的盘面字段是否正确。path 用点分隔如 'bazi.day_pillar.stem'，expected 是你认为的值。防止幻觉。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "盘面 JSON 路径，如 'bazi.day_pillar.stem'",
                    },
                    "expected": {
                        "type": "string",
                        "description": "你预期的值",
                    },
                },
                "required": ["path", "expected"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_claim",
            "description": "校验一条核心结论的三元组完整性（chart_ref + rule_ref + source_ref）。每条 Tier A 核心判断在输出前必须过此工具。返回校验结果和置信等级。",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim": {
                        "type": "string",
                        "description": "你要输出的核心结论（一句话）",
                    },
                    "chart_ref": {
                        "type": "string",
                        "description": "盘面引用路径+预期值，如 'bazi.day_pillar.stem=丁' 或 'bazi.liu_nian[0].ganzhi=丙午'。多条引用用分号分隔；路径必须带盘面体系前缀，且同一结论不能混用多个体系。",
                    },
                    "rule_ref": {
                        "type": "string",
                        "description": "规则引用 ID，如 'BZ_R_0001'。Tier A 核心判断必须提供真实存在的规则 ID。",
                    },
                    "source_ref": {
                        "type": "string",
                        "description": "典籍引用 ID，如 'ziping_zhenquan_p072'。Tier A 核心判断必须提供真实存在的典籍 ID。",
                    },
                    "tier": {
                        "type": "string",
                        "description": "结论级别：A_core=核心判断(三元组必须齐全), B_support=辅助论述(至少chart_ref), C_narrative=叙事性语言(无需引用)",
                        "enum": ["A_core", "B_support", "C_narrative"],
                    },
                },
                "required": ["claim", "chart_ref", "rule_ref", "source_ref", "tier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_safety",
            "description": "对最终输出文本做合规审查：替换绝对化用语、软化强行动建议、检测心理危机词、追加免责声明。在输出给用户前必须调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "待审查的文本",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "向用户提问以获取更多信息（如缺少出生时辰、需要确认方向等）。会阻塞等待用户回复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要问用户的问题",
                    },
                    "why": {
                        "type": "string",
                        "description": "为什么需要这个信息（展示给用户看）",
                    },
                },
                "required": ["question"],
            },
        },
    },
]


# ── 工具实现 ─────────────────────────────────────────────────

def _profile_from_birth(birth: BirthInfo) -> dict[str, Any]:
    return {
        "name": birth.name,
        "gender": birth.gender,
        "date": f"{birth.year:04d}-{birth.month:02d}-{birth.day:02d}",
        "time": f"{birth.hour:02d}:{birth.minute:02d}",
        "unknownTime": False,
        "place": birth.location_name,
        "longitude": birth.longitude,
        "latitude": birth.latitude,
        "timezone_offset": birth.timezone_offset,
    }


def _frontmatter_system(path: Path) -> str | None:
    try:
        lines = path.read_text("utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:40]:
        stripped = line.strip()
        if stripped == "---":
            return None
        if stripped.startswith("system:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")
    return None


def _system_files(directory: Path, system: str) -> list[Path]:
    return sorted(
        path
        for path in directory.glob("*.md")
        if _frontmatter_system(path) == system
    )


def _system_from_chart_ref(chart_ref: str) -> str | None:
    path = chart_ref.split("=", 1)[0].strip()
    if not path:
        return None
    prefix = path.split(".", 1)[0].split("[", 1)[0].strip()
    aliases = {
        "hexagram": "yijing",
        "natal_astro": "astrology",
        "transit_astro": "astrology",
    }
    return aliases.get(prefix, prefix)


def _split_chart_refs(chart_ref: str) -> list[str]:
    return [part.strip() for part in chart_ref.split(";") if part.strip()]


def _load_golden_cases() -> list[dict[str, Any]]:
    if not GOLDEN_CASES_PATH.exists():
        raise FileNotFoundError(f"专业黄金集不存在: {GOLDEN_CASES_PATH}")
    data = json.loads(GOLDEN_CASES_PATH.read_text("utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("专业黄金集格式错误：缺少 cases 列表。")
    return cases


def _rg_search(directory: Path, pattern: str, system: str | None = None) -> str:
    """用 ripgrep 搜索目录，返回格式化结果。"""
    cmd = ["rg", "--max-count=5", "--no-heading", "-i", "--"]
    if system:
        files = _system_files(directory, system)
        if not files:
            return f"未找到 {system} 体系资料。"
        cmd.append(pattern)
        cmd.extend(str(path) for path in files)
    else:
        cmd.extend([pattern, str(directory)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        output = result.stdout.strip()
        if not output:
            return "未找到匹配结果。"
        # 截断避免 token 爆炸
        lines = output.split("\n")
        if len(lines) > 20:
            lines = lines[:20]
            lines.append(f"... (共匹配更多，仅显示前 20 行)")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "搜索超时。"
    except FileNotFoundError:
        return "ripgrep (rg) 未安装。"


def _resolve_json_path(obj: Any, path: str) -> tuple[bool, Any]:
    """解析 JSON path，支持 ``foo.bar[0].baz``。"""
    cur = obj
    for raw_part in path.split("."):
        part = raw_part.strip()
        if not part:
            continue
        while part:
            if part.startswith("["):
                close = part.find("]")
                if close <= 1:
                    return False, None
                index_text = part[1:close].strip()
                if not index_text.isdigit() or not isinstance(cur, list):
                    return False, None
                idx = int(index_text)
                if idx >= len(cur):
                    return False, None
                cur = cur[idx]
                part = part[close + 1:]
                continue

            bracket = part.find("[")
            key = part if bracket == -1 else part[:bracket]
            if key.isdigit() and isinstance(cur, list):
                idx = int(key)
                if idx >= len(cur):
                    return False, None
                cur = cur[idx]
            elif isinstance(cur, dict):
                if key not in cur:
                    return False, None
                cur = cur[key]
            elif hasattr(cur, key):
                cur = getattr(cur, key)
            else:
                return False, None
            if bracket == -1:
                part = ""
            else:
                part = part[bracket:]
    return True, cur


class ToolExecutor:
    """持有 session 上下文的工具执行器。"""

    def __init__(self, birth: BirthInfo, charts: Charts, question: str = "",
                 profile: dict | None = None):
        self.birth = birth
        self.charts = charts
        self.question = question
        self.profile = profile or _profile_from_birth(birth)
        self._loaded_skills: set[str] = set()

    async def dispatch(self, tool_name: str, args: dict) -> dict:
        """执行工具，返回 {result: ..., error: ...}。"""
        fn = getattr(self, f"_tool_{tool_name}", None)
        if fn is None:
            return {"error": f"未知工具: {tool_name}"}
        try:
            result = await fn(args)
            return {"result": result}
        except IntakeError as e:
            logger.info("Tool %s blocked by intake contract: %s", tool_name, e)
            return {
                "error": str(e),
                "error_type": "intake",
                "issues": [
                    {
                        "field": issue.field,
                        "message": issue.message,
                        "blocking": issue.blocking,
                    }
                    for issue in e.issues
                ],
            }
        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            return {"error": str(e)}

    async def _tool_load_skill(self, args: dict) -> str:
        name = args["name"]
        if name in self._loaded_skills:
            return f"[技能 {name} 已加载，无需重复加载]"
        skill_path = SKILLS_DIR / name / "SKILL.md"
        if not skill_path.exists():
            return f"技能 {name} 不存在。可用: {', '.join(s.stem for s in SKILLS_DIR.iterdir() if s.is_dir() or s.suffix == '.md')}"
        content = skill_path.read_text("utf-8")
        self._loaded_skills.add(name)
        return content

    async def _tool_compute_chart(self, args: dict) -> str:
        chart_type = args["chart_type"]
        assert_chart_ready(chart_type, self.profile, self.question)
        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year

        if chart_type == "bazi":
            from computation.bazi import compute_bazi
            self.charts.bazi = compute_bazi(self.birth, current_year=current_year)
            return json.dumps(self.charts.bazi.model_dump(), ensure_ascii=False, indent=1)

        if chart_type == "ziwei":
            from computation.ziwei import compute_ziwei
            self.charts.ziwei = compute_ziwei(self.birth)
            return json.dumps(self.charts.ziwei.model_dump(), ensure_ascii=False, indent=1)

        if chart_type == "hexagram":
            from computation.yijing import compute_coin, compute_meihua
            divination_time = datetime.fromisoformat(self.profile["divination_time"])
            if self.profile.get("coin_results"):
                self.charts.hexagram = compute_coin(
                    self.question,
                    coin_results=self.profile["coin_results"],
                    dt=divination_time,
                )
            else:
                numbers = self.profile.get("hexagram_numbers")
                number_tuple = tuple(int(x) for x in numbers) if numbers else None
                self.charts.hexagram = compute_meihua(
                    self.question,
                    numbers=number_tuple,
                    dt=divination_time,
                )
            return json.dumps(self.charts.hexagram.model_dump(), ensure_ascii=False, indent=1)

        if chart_type == "fengshui":
            from computation.fengshui import compute_fengshui
            facing_degree = float(self.profile["facing_degree"])
            move_in_year = int(self.profile.get("move_in_year") or self.profile.get("built_year"))
            self.charts.fengshui = compute_fengshui(facing_degree, self.birth, move_in_year=move_in_year)
            return json.dumps(self.charts.fengshui.model_dump(), ensure_ascii=False, indent=1)

        if chart_type == "natal_astro":
            from computation.astrology import compute_natal_chart
            self.charts.natal_astro = compute_natal_chart(self.birth)
            return json.dumps(self.charts.natal_astro.model_dump(), ensure_ascii=False, indent=1)

        if chart_type == "transit_astro":
            from computation.astrology import compute_natal_chart, compute_transits
            if not self.charts.natal_astro:
                self.charts.natal_astro = compute_natal_chart(self.birth)
            self.charts.transit_astro = compute_transits(
                self.charts.natal_astro, now_utc, self.birth
            )
            return json.dumps(self.charts.transit_astro.model_dump(), ensure_ascii=False, indent=1)

        if chart_type == "tarot":
            from computation.tarot import draw_tarot
            self.charts.tarot = draw_tarot(
                self.question,
                spread=self.profile["tarot_spread"],
                card_indexes=self.profile.get("tarot_card_indexes"),
                reversed_flags=self.profile.get("tarot_reversed_flags"),
            )
            return json.dumps(self.charts.tarot.model_dump(), ensure_ascii=False, indent=1)

        if chart_type == "numerology":
            from computation.numerology import compute_numerology
            self.charts.numerology = compute_numerology(
                self.birth, current_year=current_year, full_name_pinyin=self.birth.name
            )
            return json.dumps(self.charts.numerology.model_dump(), ensure_ascii=False, indent=1)

        return f"未知盘面类型: {chart_type}"

    async def _tool_update_profile(self, args: dict) -> str:
        updates: dict[str, Any] = {}

        def set_field(name: str, value: Any) -> None:
            self.profile[name] = value
            updates[name] = value

        if "gender" in args and args["gender"] is not None:
            gender = str(args["gender"])
            if gender not in {"male", "female", "other"}:
                raise ValueError("gender 只能是 male / female / other。")
            set_field("gender", gender)
            self.birth.gender = gender  # type: ignore[assignment]

        if "facing_degree" in args and args["facing_degree"] is not None:
            facing_degree = float(args["facing_degree"])
            if not 0 <= facing_degree < 360:
                raise ValueError("facing_degree 必须在 [0, 360) 范围内。")
            set_field("facing_degree", facing_degree)

        for year_field in ("move_in_year", "built_year"):
            if year_field in args and args[year_field] is not None:
                year = int(args[year_field])
                if not 1800 <= year <= 2200:
                    raise ValueError(f"{year_field} 年份超出可接受范围。")
                set_field(year_field, year)

        if "hexagram_numbers" in args and args["hexagram_numbers"] is not None:
            numbers = [int(x) for x in args["hexagram_numbers"]]
            if len(numbers) not in (2, 3):
                raise ValueError("hexagram_numbers 必须是 2 或 3 个数字。")
            set_field("hexagram_numbers", numbers)

        if "coin_results" in args and args["coin_results"] is not None:
            coins = args["coin_results"]
            if (
                not isinstance(coins, list)
                or len(coins) != 6
                or any(not isinstance(row, list) or len(row) != 3 for row in coins)
            ):
                raise ValueError("coin_results 必须是 6 组、每组 3 枚铜钱结果。")
            normalized = [[int(x) for x in row] for row in coins]
            if any(x not in (0, 1) for row in normalized for x in row):
                raise ValueError("coin_results 只能使用 0/1。")
            set_field("coin_results", normalized)

        if "divination_time" in args and args["divination_time"] is not None:
            divination_time = str(args["divination_time"])
            datetime.fromisoformat(divination_time)
            set_field("divination_time", divination_time)

        if "tarot_spread" in args and args["tarot_spread"] is not None:
            set_field("tarot_spread", str(args["tarot_spread"]))

        if "tarot_card_indexes" in args and args["tarot_card_indexes"] is not None:
            indexes = [int(x) for x in args["tarot_card_indexes"]]
            if not indexes:
                raise ValueError("tarot_card_indexes 不能为空。")
            set_field("tarot_card_indexes", indexes)

        if "tarot_reversed_flags" in args and args["tarot_reversed_flags"] is not None:
            flags = [bool(x) for x in args["tarot_reversed_flags"]]
            set_field("tarot_reversed_flags", flags)

        if not updates:
            raise ValueError("update_profile 未收到任何明确可写字段。")
        return json.dumps({"updated": updates}, ensure_ascii=False, indent=1)

    async def _tool_grep_classics(self, args: dict) -> str:
        return _rg_search(CLASSICS_DIR, args["pattern"], args.get("system"))

    async def _tool_read_classic(self, args: dict) -> str:
        cid = args["id"].replace(".md", "")
        path = CLASSICS_DIR / f"{cid}.md"
        if not path.exists():
            return f"典籍 {cid} 不存在。"
        return path.read_text("utf-8")

    async def _tool_grep_rules(self, args: dict) -> str:
        return _rg_search(RULES_DIR, args["pattern"], args.get("system"))

    async def _tool_read_rule(self, args: dict) -> str:
        rid = args["id"].replace(".md", "")
        path = RULES_DIR / f"{rid}.md"
        if not path.exists():
            return f"规则 {rid} 不存在。"
        return path.read_text("utf-8")

    async def _tool_load_golden_cases(self, args: dict) -> str:
        system = str(args["system"])
        if system not in {"bazi", "ziwei", "yijing", "fengshui"}:
            raise ValueError("load_golden_cases 只支持 bazi / ziwei / yijing / fengshui。")
        limit = int(args.get("limit") or 3)
        if not 1 <= limit <= 10:
            raise ValueError("limit 必须在 1 到 10 之间。")

        matches = [case for case in _load_golden_cases() if case.get("system") == system]
        if not matches:
            raise ValueError(f"专业黄金集中没有 {system} 案例，不能伪造参考案例。")

        result = []
        for case in matches[:limit]:
            result.append({
                "id": case.get("id"),
                "system": case.get("system"),
                "source_type": case.get("source_type"),
                "question": case.get("question"),
                "expected": case.get("expected", {}),
                "interpretation_anchors": case.get("interpretation_anchors", []),
            })
        return json.dumps({"cases": result}, ensure_ascii=False, indent=1)

    async def _tool_verify_chart_ref(self, args: dict) -> str:
        path = args["path"]
        expected = args["expected"]
        charts_dict = self.charts.model_dump()
        found, actual = _resolve_json_path(charts_dict, path)
        if not found:
            return f"❌ 路径 {path} 不存在于盘面中。请检查路径拼写。"
        actual_str = str(actual).strip()
        expected_str = str(expected).strip()
        if expected_str == actual_str:
            return f"✓ {path} = {actual}（与预期 {expected} 一致）"
        if isinstance(actual, list) and expected_str in [str(x).strip() for x in actual]:
            return f"✓ {path} 包含 {expected}（实际列表: {actual}）"
        return f"❌ 不一致！{path} = {actual}，但你说的是 {expected}。请修正你的论述。"

    async def _tool_verify_claim(self, args: dict) -> str:
        """三元组校验：chart_ref 查盘面，rule_ref 查规则文件是否存在，source_ref 查典籍文件是否存在。"""
        claim = args["claim"]
        chart_ref = args.get("chart_ref", "")
        rule_ref = args.get("rule_ref", "none")
        source_ref = args.get("source_ref", "none")
        tier = args.get("tier", "A_core")

        issues: list[str] = []
        checks: list[str] = []
        chart_system = None

        def _missing_ref(value: str | None) -> bool:
            return not value or value.strip().lower() in {"none", "null", "n/a", "na", "无"}

        # 1. chart_ref 验证 — 解析 path=expected 格式
        if not _missing_ref(chart_ref):
            chart_refs = _split_chart_refs(chart_ref)
            chart_systems = {_system_from_chart_ref(ref) for ref in chart_refs}
            chart_systems.discard(None)
            if len(chart_systems) > 1:
                issues.append(f"CHART_SYSTEM_MISMATCH: 同一结论引用了多个盘面体系 {sorted(chart_systems)}")
            chart_system = next(iter(chart_systems), None)

            for ref in chart_refs:
                if "=" not in ref:
                    issues.append(f"BAD_REF: chart_ref 格式应为 'path=value'，收到: {ref}")
                    continue
                path, expected = ref.split("=", 1)
                charts_dict = self.charts.model_dump()
                found, actual = _resolve_json_path(charts_dict, path.strip())
                if not found:
                    issues.append(f"FACT_VIOLATION: chart_ref 路径 '{path}' 不存在于盘面中")
                else:
                    expected_value = str(expected).strip()
                    if isinstance(actual, list):
                        matched = expected_value in [str(x).strip() for x in actual]
                    else:
                        matched = expected_value == str(actual).strip()
                    if not matched:
                        issues.append(f"FACT_VIOLATION: {path}={actual}，但你说的是 {expected}")
                    else:
                        checks.append(f"✓ chart_ref: {path}={actual}")
        elif tier == "A_core":
            issues.append("MISSING: Tier A 核心判断缺少 chart_ref")
        elif tier == "B_support":
            issues.append("MISSING: Tier B 辅助论述缺少 chart_ref")

        # 2. rule_ref 验证 — 检查规则文件是否存在
        if not _missing_ref(rule_ref):
            rid = rule_ref.replace(".md", "")
            rule_path = RULES_DIR / f"{rid}.md"
            if rule_path.exists():
                rule_system = _frontmatter_system(rule_path)
                if chart_system and not rule_system:
                    issues.append(f"RULE_SYSTEM_MISSING: 规则 {rid} 缺少 system frontmatter，不能用于核心结论")
                elif chart_system and rule_system != chart_system:
                    issues.append(f"RULE_SYSTEM_MISMATCH: 规则 {rid} 属于 {rule_system}，但 chart_ref 属于 {chart_system}")
                else:
                    checks.append(f"✓ rule_ref: {rid} 存在")
            else:
                issues.append(f"RULE_MISSING: 规则 {rid} 不在库中")
        elif tier == "A_core":
            issues.append("MISSING: Tier A 核心判断缺少 rule_ref")

        # 3. source_ref 验证 — 检查典籍文件是否存在
        if not _missing_ref(source_ref):
            sid = source_ref.replace(".md", "")
            source_path = CLASSICS_DIR / f"{sid}.md"
            if source_path.exists():
                source_system = _frontmatter_system(source_path)
                if chart_system and not source_system:
                    issues.append(f"SOURCE_SYSTEM_MISSING: 典籍 {sid} 缺少 system frontmatter，不能用于核心结论")
                elif chart_system and source_system != chart_system:
                    issues.append(f"SOURCE_SYSTEM_MISMATCH: 典籍 {sid} 属于 {source_system}，但 chart_ref 属于 {chart_system}")
                else:
                    checks.append(f"✓ source_ref: {sid} 存在")
            else:
                issues.append(f"SOURCE_MISSING: 典籍 {sid} 不在库中")
        elif tier == "A_core":
            issues.append("MISSING: Tier A 核心判断缺少 source_ref")

        # 判定
        has_fact_violation = any("FACT_VIOLATION" in i for i in issues)
        if has_fact_violation or (tier == "A_core" and issues):
            verdict = "❌ REJECTED — 核心结论证据链不完整或盘面事实不符，此结论不可输出，必须修正。"
        elif issues:
            verdict = "⚠ SOFT_FLAG — 存在引用缺失/偏差，建议补充或标注置信度偏低。"
        else:
            verdict = "✅ VERIFIED — 三元组完整，可输出。"

        parts = [f"结论: {claim}", f"级别: {tier}", verdict]
        if checks:
            parts.append("通过: " + " | ".join(checks))
        if issues:
            parts.append("问题: " + " | ".join(issues))

        return "\n".join(parts)

    async def _tool_apply_safety(self, args: dict) -> str:
        from agents.safety import apply_safety as _apply
        text, triggers = _apply(args["text"])
        if triggers:
            return json.dumps({"text": text, "triggers": triggers}, ensure_ascii=False)
        return text
