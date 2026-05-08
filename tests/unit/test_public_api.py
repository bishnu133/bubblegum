from bubblegum import (
    act,
    clear_vision_provider,
    configure_runtime,
    configure_vision_provider,
    extract,
    recover,
    verify,
)


def test_top_level_public_api_exports_exist():
    assert callable(act)
    assert callable(verify)
    assert callable(extract)
    assert callable(recover)
    assert callable(configure_runtime)
    assert callable(configure_vision_provider)
    assert callable(clear_vision_provider)
