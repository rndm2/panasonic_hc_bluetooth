"""Narrow, idempotent ESP-IDF 5.5.6 SMP bond-reuse correction."""

from pathlib import Path

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
        assert previous not in handler, "Unexpected partially modified SDK handler"
        return source
    assert handler.count(previous) == 1, "SDK handler changed; review before applying"
    return source[:start] + handler.replace(previous, corrected) + source[end:]
