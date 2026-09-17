from app.analysis.catalog import is_catalog_question


def test_catalog_intent_requires_catalog_specific_language() -> None:
    assert is_catalog_question("为什么商品目录整体转化率下降？") is True
    assert is_catalog_question("哪些商品曝光高但点击率低？") is True
    assert is_catalog_question("为什么客户访问到下单的转化率下降？") is False
    assert is_catalog_question("分析收入变化") is False
