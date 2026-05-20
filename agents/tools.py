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
            "description": "加载一个命理技能的完整方法论到上下文。技能会教你怎么用其它工具做这个系统的解读。可用技能: bazi, ziwei, yijing, fengshui, astrology, tarot, numerology, cross_synthesis",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名称",
                        "enum": ["bazi", "ziwei", "yijing", "fengshui", "astrology", "tarot", "numerology", "cross_synthesis"],
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
            "description": "计算命理盘面，返回完整 JSON 结构（四柱、宫位、行星等）。盘面数据来自此工具的计算结果。",
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
            "description": "把用户明确补充的事实写入本轮计算档案。记录用户明确提供的字段，常用于 ask_user 后补入性别、风水朝向/入住年、起卦输入、塔罗抽牌结果。",
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
            "description": "读取同体系专业黄金案例。提供人工盘例的事实锚点、取象方式和解释锚点，作为解读参考。",
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
    {
        "type": "function",
        "function": {
            "name": "recompute_chart",
            "description": "用修正后的出生信息重新计算盘面。当用户反馈出生时间可能有偏差时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "system": {
                        "type": "string",
                        "enum": ["bazi", "ziwei", "astrology"],
                        "description": "要重算的体系",
                    },
                    "hour_offset": {
                        "type": "integer",
                        "description": "小时偏移（-2 到 +2），比如用户说'可能早一小时'则传 -1",
                    },
                    "minute_offset": {
                        "type": "integer",
                        "description": "分钟偏移（-120 到 +120）",
                    },
                },
                "required": ["system"],
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


def _llm_chart_dump(chart_type: str, chart: Any) -> dict[str, Any]:
    data = chart.model_dump()
    if chart_type != "ziwei":
        return data

    return {
        "life_palace": data.get("life_palace"),
        "body_palace": data.get("body_palace"),
        "five_element_bureau": data.get("five_element_bureau"),
        "si_hua": data.get("si_hua", {}),
        "main_stars": data.get("main_stars", {}),
        "palaces_by_name": data.get("palaces_by_name", {}),
        "da_xian": data.get("da_xian", []),
        "metadata": {
            key: value
            for key, value in data.get("metadata", {}).items()
            if key in {
                "engine",
                "engine_version",
                "effective_datetime",
                "time",
                "time_range",
                "lunar_date",
                "soul_palace_branch",
                "body_palace_branch",
                "soul_star",
                "body_star",
                "focus",
                "calibration_questions",
            }
        },
    }


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
        dir_prefix = str(directory) + "/"
        output = output.replace(dir_prefix, "")
        lines = output.split("\n")
        if len(lines) > 20:
            lines = lines[:20]
            lines.append(f"... (共匹配更多，仅显示前 20 行)")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "搜索超时。"
    except FileNotFoundError:
        return "ripgrep (rg) 未安装。"



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
            return json.dumps(_llm_chart_dump(chart_type, self.charts.bazi), ensure_ascii=False, indent=1)

        if chart_type == "ziwei":
            from computation.ziwei import compute_ziwei
            self.charts.ziwei = compute_ziwei(self.birth)
            return json.dumps(_llm_chart_dump(chart_type, self.charts.ziwei), ensure_ascii=False, indent=1)

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
            return json.dumps(_llm_chart_dump(chart_type, self.charts.hexagram), ensure_ascii=False, indent=1)

        if chart_type == "fengshui":
            from computation.fengshui import compute_fengshui
            facing_degree = float(self.profile["facing_degree"])
            move_in_year = int(self.profile.get("move_in_year") or self.profile.get("built_year"))
            self.charts.fengshui = compute_fengshui(facing_degree, self.birth, move_in_year=move_in_year)
            return json.dumps(_llm_chart_dump(chart_type, self.charts.fengshui), ensure_ascii=False, indent=1)

        if chart_type == "natal_astro":
            from computation.astrology import compute_natal_chart
            self.charts.natal_astro = compute_natal_chart(self.birth)
            return json.dumps(_llm_chart_dump(chart_type, self.charts.natal_astro), ensure_ascii=False, indent=1)

        if chart_type == "transit_astro":
            from computation.astrology import compute_natal_chart, compute_transits
            if not self.charts.natal_astro:
                self.charts.natal_astro = compute_natal_chart(self.birth)
            self.charts.transit_astro = compute_transits(
                self.charts.natal_astro, now_utc, self.birth
            )
            return json.dumps(_llm_chart_dump(chart_type, self.charts.transit_astro), ensure_ascii=False, indent=1)

        if chart_type == "tarot":
            from computation.tarot import draw_tarot
            self.charts.tarot = draw_tarot(
                self.question,
                spread=self.profile["tarot_spread"],
                card_indexes=self.profile.get("tarot_card_indexes"),
                reversed_flags=self.profile.get("tarot_reversed_flags"),
            )
            return json.dumps(_llm_chart_dump(chart_type, self.charts.tarot), ensure_ascii=False, indent=1)

        if chart_type == "numerology":
            from computation.numerology import compute_numerology
            self.charts.numerology = compute_numerology(
                self.birth, current_year=current_year, full_name_pinyin=self.birth.name
            )
            return json.dumps(_llm_chart_dump(chart_type, self.charts.numerology), ensure_ascii=False, indent=1)

        return f"未知盘面类型: {chart_type}"

    async def _tool_recompute_chart(self, args: dict) -> dict:
        """用修正后的出生时间重新计算盘面。"""
        system = args["system"]
        hour_offset = args.get("hour_offset", 0)
        minute_offset = args.get("minute_offset", 0)
        total_minutes = hour_offset * 60 + minute_offset

        if not -120 <= total_minutes <= 120:
            return {"error": "偏移量超出范围，合计须在 -120 到 +120 分钟之间。"}

        from datetime import timedelta
        original_dt = datetime(self.birth.year, self.birth.month, self.birth.day,
                               self.birth.hour, self.birth.minute)
        adjusted_dt = original_dt + timedelta(minutes=total_minutes)

        adjusted_birth = self.birth.model_copy(update={
            "year": adjusted_dt.year,
            "month": adjusted_dt.month,
            "day": adjusted_dt.day,
            "hour": adjusted_dt.hour,
            "minute": adjusted_dt.minute,
        })

        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year
        offset_desc = f"{'+' if total_minutes >= 0 else ''}{total_minutes} 分钟"

        if system == "bazi":
            from computation.bazi import compute_bazi
            chart = compute_bazi(adjusted_birth, current_year=current_year)
            self.charts.bazi = chart
            return {
                "offset_applied": offset_desc,
                "adjusted_time": adjusted_dt.strftime("%Y-%m-%d %H:%M"),
                "chart": json.loads(json.dumps(
                    _llm_chart_dump("bazi", chart), ensure_ascii=False, indent=1
                )),
            }
        elif system == "ziwei":
            from computation.ziwei import compute_ziwei
            chart = compute_ziwei(adjusted_birth)
            self.charts.ziwei = chart
            return {
                "offset_applied": offset_desc,
                "adjusted_time": adjusted_dt.strftime("%Y-%m-%d %H:%M"),
                "chart": json.loads(json.dumps(
                    _llm_chart_dump("ziwei", chart), ensure_ascii=False, indent=1
                )),
            }
        elif system == "astrology":
            from computation.astrology import compute_natal_chart
            chart = compute_natal_chart(adjusted_birth)
            self.charts.natal_astro = chart
            return {
                "offset_applied": offset_desc,
                "adjusted_time": adjusted_dt.strftime("%Y-%m-%d %H:%M"),
                "chart": json.loads(json.dumps(
                    _llm_chart_dump("natal_astro", chart), ensure_ascii=False, indent=1
                )),
            }
        else:
            return {"error": f"不支持重算的体系: {system}"}

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
            raise ValueError(f"专业黄金集中没有 {system} 案例。")

        result = []
        for case in matches[:limit]:
            result.append({
                "id": case.get("id"),
                "system": case.get("system"),
                "source_type": case.get("source_type"),
                "question": case.get("question"),
                "chart_facts": case.get("expected", {}),
                "interpretation_anchors": case.get("interpretation_anchors", []),
            })
        return json.dumps({"cases": result}, ensure_ascii=False, indent=1)
