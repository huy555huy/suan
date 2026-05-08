"""把 chart_type 映射到对应的 computation 模块入口。

各计算模块由并行 agent 实现：
- bazi.py: compute_bazi(birth, current_year)
- ziwei.py: compute_ziwei(birth)
- yijing.py: compute_meihua(question, ...) / compute_coin(...)
- fengshui.py: compute_fengshui(facing_degree, birth, move_in_year)
- astrology.py: compute_natal_chart(birth) / compute_transits(natal, target_date, birth)
- tarot.py: draw_tarot(question, spread, ...)
- numerology.py: compute_numerology(birth, current_year, full_name_pinyin)
"""
from __future__ import annotations
import logging
from datetime import datetime
import importlib

from core.schemas import AgentState, BirthInfo

logger = logging.getLogger("suan.compute")


async def dispatch_compute(chart_type: str, state: AgentState) -> None:
    """给 state.charts 填充对应类型的盘面。"""
    birth = state.birth
    current_year = datetime.utcnow().year

    if chart_type == "bazi":
        try:
            from computation import bazi
            chart = bazi.compute_bazi(birth, current_year=current_year)
            state.charts.bazi = chart
        except Exception as e:
            logger.warning("bazi compute failed: %s", e)
            state.errors.append(f"bazi:{e}")
        return

    if chart_type == "ziwei":
        try:
            from computation import ziwei
            chart = ziwei.compute_ziwei(birth)
            state.charts.ziwei = chart
        except Exception as e:
            logger.warning("ziwei compute failed: %s", e)
            state.errors.append(f"ziwei:{e}")
        return

    if chart_type == "hexagram":
        try:
            from computation import yijing
            chart = yijing.compute_meihua(state.question, dt=datetime.utcnow())
            state.charts.hexagram = chart
        except Exception as e:
            logger.warning("yijing compute failed: %s", e)
            state.errors.append(f"yijing:{e}")
        return

    if chart_type == "fengshui":
        try:
            from computation import fengshui
            facing = float((state.birth.metadata or {}).get("facing_degree", 180.0)) \
                if hasattr(state.birth, "metadata") else 180.0
            chart = fengshui.compute_fengshui(facing, birth)
            state.charts.fengshui = chart
        except Exception as e:
            logger.warning("fengshui compute failed: %s", e)
            state.errors.append(f"fengshui:{e}")
        return

    if chart_type == "natal_astro":
        try:
            from computation import astrology
            chart = astrology.compute_natal_chart(birth)
            state.charts.natal_astro = chart
        except Exception as e:
            logger.warning("astrology compute failed: %s", e)
            state.errors.append(f"natal_astro:{e}")
        return

    if chart_type == "transit_astro":
        try:
            from computation import astrology
            if not state.charts.natal_astro:
                natal = astrology.compute_natal_chart(birth)
                state.charts.natal_astro = natal
            transits = astrology.compute_transits(state.charts.natal_astro,
                                                    datetime.utcnow(), birth)
            state.charts.transit_astro = transits
        except Exception as e:
            logger.warning("transit compute failed: %s", e)
            state.errors.append(f"transit:{e}")
        return

    if chart_type == "tarot":
        try:
            from computation import tarot
            chart = tarot.draw_tarot(state.question, spread="celtic_cross")
            state.charts.tarot = chart
        except Exception as e:
            logger.warning("tarot compute failed: %s", e)
            state.errors.append(f"tarot:{e}")
        return

    if chart_type == "numerology":
        try:
            from computation import numerology
            chart = numerology.compute_numerology(birth, current_year=current_year,
                                                    full_name_pinyin=birth.name)
            state.charts.numerology = chart
        except Exception as e:
            logger.warning("numerology compute failed: %s", e)
            state.errors.append(f"numerology:{e}")
        return
