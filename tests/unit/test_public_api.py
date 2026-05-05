from bubblegum import act, configure_runtime, extract, recover, verify


def test_top_level_public_api_exports_exist():
    assert callable(act)
    assert callable(verify)
    assert callable(extract)
    assert callable(recover)
    assert callable(configure_runtime)
