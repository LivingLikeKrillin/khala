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
        try:
            work_item, result = json.loads(line)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ValueError(f"Malformed JSONL line: {line!r}") from exc
        if result is None:
            continue
        if result.get("worker_outcome") != "normal":
            continue
        if result.get("test_outcome") != "survived":
            continue
        # cosmic-ray's local distributor emits one mutation per work_item; [0] is that mutation.
        mutation = work_item["mutations"][0]
        survivors.append(
            Survivor(
                module=mutation["module_path"].replace("\\", "/"),
                lineno=mutation["start_pos"][0],
                operator=mutation["operator_name"],
                mutation_diff=result.get("diff", ""),
            )
        )
    return survivors
