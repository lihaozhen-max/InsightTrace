from app.analysis.behavior import is_behavior_question


def test_behavior_intent_requires_customer_behavior_language() -> None:
    assert is_behavior_question("为什么本周访问到下单的转化率下降？") is True
    assert is_behavior_question("新客和老客的行为差异是什么？") is True
    assert is_behavior_question("为什么商品目录整体转化率下降？") is False
    assert is_behavior_question("分析收入变化") is False
