import json

from mutqa.models import Survivor


def extract_survivors(dump_text: str) -> list[Survivor]:
    """cosmic-ray `dump` 출력(JSONL)에서 살아남은 변이만 추출.

    각 줄 = [work_item, work_result]. survivor = work_result 비-null이며
    worker_outcome == "normal" AND test_outcome == "survived".
    """
    survivors: list[Survivor] = []
    for line in dump_text.splitlines():
        line = line.strip()
        if not line:
            continue
        work_item, result = json.loads(line)
        if result is None:
            continue
        if result.get("worker_outcome") != "normal":
            continue
        if result.get("test_outcome") != "survived":
            continue
        survivors.append(
            Survivor(
                module=work_item["module_path"],
                lineno=work_item["start_pos"][0],
                operator=work_item["operator_name"],
                mutation_diff=result.get("diff", ""),
            )
        )
    return survivors
