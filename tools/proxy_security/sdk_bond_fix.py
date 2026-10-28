"""Narrow, idempotent ESP-IDF 5.5.6 SMP bond-reuse correction."""

from pathlib import Path

SDK_VERSION = "5.5.6"
EXPECTED_SOURCE_SHA256 = "67ef3fd8405ec42e3dfbe66fedce043d5de6b4ac7521122e969572c41004b6f8"
SDK_RELATIVE_SOURCE = Path("components/bt/host/bluedroid/stack/smp/smp_act.c")


def fix_source(source: str) -> str:
    """Clear old keys only when encryption follows a new pairing exchange."""
    start = source.index("void smp_check_auth_req(")
    end = source.find(
        "/*******************************************************************************", start
    )
    if end < 0:
        end = len(source)
    handler = source[start:end]
    previous = "if (p_dev_rec) {"
    corrected = "if (p_dev_rec && (p_cb->flags & SMP_PAIR_FLAG_ENC_AFTER_PAIR)) {"
    if corrected in handler:
        if previous in handler:
            raise ValueError("Unexpected partially modified SDK handler")
        return source
    if handler.count(previous) != 1:
        raise ValueError("SDK handler changed; review before applying")
    return source[:start] + handler.replace(previous, corrected) + source[end:]
