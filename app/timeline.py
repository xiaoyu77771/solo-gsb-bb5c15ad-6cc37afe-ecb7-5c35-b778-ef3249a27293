"""时间轴换算：把展开后的实际演奏路径映射为毫秒时间轴。

语义
----
* 每个小节声明正数拍数 ``beats``；速度标记 ``tempo_bpm`` 写在小节上，
  自该小节起生效，直到下一个速度标记。
* 首小节必须给出速度；反复或 D.C./D.S. 折返后再次经过速度标记时，
  标记重新生效（该小节及之后恢复为标记速度）。
* 小节时长 = beats * 60000 / tempo_bpm 毫秒。内部以浮点累计、全程不
  逐步取整；毫秒仅在输出时四舍五入，因此相邻步骤的 end_ms / start_ms
  始终衔接。
"""

from __future__ import annotations

import math

from .errors import StructuralError
from .expander import PlayedStep
from .models import TimelineMeasure, TimelineStep

_MS_PER_MINUTE = 60_000.0


def check_timeline_values(measures: list[TimelineMeasure]) -> list[StructuralError]:
    """校验拍数与速度：beats / tempo_bpm 必须为正的有限数；首小节必须给出速度。"""
    errors: list[StructuralError] = []
    for m in measures:
        if not math.isfinite(m.beats) or m.beats <= 0:
            errors.append(
                StructuralError(
                    "INVALID_BEATS",
                    f"小节拍数 beats 必须为正数，实际为 {m.beats}",
                    m.measure,
                )
            )
        if m.tempo_bpm is not None and (
            not math.isfinite(m.tempo_bpm) or m.tempo_bpm <= 0
        ):
            errors.append(
                StructuralError(
                    "INVALID_TEMPO",
                    f"速度 tempo_bpm 必须为正数 BPM，实际为 {m.tempo_bpm}",
                    m.measure,
                )
            )
    if measures and measures[0].tempo_bpm is None:
        errors.append(
            StructuralError(
                "TEMPO_REQUIRED",
                "首小节必须给出速度 tempo_bpm（后续小节的速度标记可选）",
                measures[0].measure,
            )
        )
    return errors


def _round_ms(value: float) -> int:
    """毫秒输出取整：四舍五入（half up）。仅在输出时调用，内部累计不使用。"""
    return int(math.floor(value + 0.5))


def build_timeline(
    measures: list[TimelineMeasure], played: list[PlayedStep]
) -> tuple[list[TimelineStep], int]:
    """把展开后的演奏路径换算为时间轴，返回 (steps, total_duration_ms)。

    调用前须通过 ``check_timeline_values`` 与结构校验，因此首小节必有
    合法速度标记，演奏路径第一步即可确定初始速度。
    """
    beats_of = {m.measure: m.beats for m in measures}
    tempo_mark = {m.measure: m.tempo_bpm for m in measures if m.tempo_bpm is not None}

    steps: list[TimelineStep] = []
    occurrences: dict[int, int] = {}
    tempo = 0.0  # 首步即被首小节的速度标记覆盖（校验已保证其存在）
    cursor = 0.0  # 内部累计毫秒：全程不取整

    for s in played:
        mark = tempo_mark.get(s.measure)
        if mark is not None:
            tempo = mark  # 反复 / D.C./D.S. 再次经过速度标记时重新生效
        duration = beats_of[s.measure] * _MS_PER_MINUTE / tempo
        start, cursor = cursor, cursor + duration
        occurrences[s.measure] = occurrences.get(s.measure, 0) + 1
        steps.append(
            TimelineStep(
                occurrence=occurrences[s.measure],
                measure=s.measure,
                start_ms=_round_ms(start),
                end_ms=_round_ms(cursor),
                tempo_bpm=tempo,
            )
        )
    return steps, _round_ms(cursor)
