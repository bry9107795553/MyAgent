"""
测试秘书机制 — 验证否定检测、失败检测、纠错触发、摘要生成
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from myagent.domain.agents.secretary import (
    Secretary, RuntimeState, NEGATION_PATTERNS, FAILURE_PATTERNS,
)


def test_runtime_state():
    """测试 RuntimeState 的序列化/反序列化"""
    print("=" * 60)
    print("测试 1: RuntimeState 持久化")
    
    state = RuntimeState(
        active_project="test_project",
        current_phase="Phase 2",
        completed_modules=["Header", "NavBar"],
        in_progress_module="TaskCard",
        total_turns=10,
        turns_since_last_summary=5,
        consecutive_failures=2,
        user_negation_count=1,
        active_role_id="coach",
    )
    
    # 序列化
    d = state.to_dict()
    assert d["active_project"] == "test_project"
    assert d["completed_modules"] == ["Header", "NavBar"]
    assert d["consecutive_failures"] == 2
    
    # 反序列化
    restored = RuntimeState.from_dict(d)
    assert restored.active_project == state.active_project
    assert restored.consecutive_failures == state.consecutive_failures
    assert restored.completed_modules == state.completed_modules
    
    print("  ✓ 序列化/反序列化通过")


def test_negation_detection():
    """测试否定关键词检测"""
    print("\n" + "=" * 60)
    print("测试 2: 否定检测")
    
    secretary = Secretary()
    secretary.init("test_negation", state_dir="data/test")
    
    # 应该触发否定
    positive_cases = [
        "不对",
        "你错了",
        "我不是这个意思",
        "神经病，你怎么又搞错了",
        "你到底有没有在听",
        "我要的是 Vue 不是 React",
    ]
    
    for msg in positive_cases:
        assert secretary._detect_negation(msg), f"应检测到否定: {msg}"
    
    # 不应触发否定
    negative_cases = [
        "好的，继续",
        "这个方案可以",
        "帮我看看这个代码",
        "你觉得 React 和 Vue 哪个好",
    ]
    
    for msg in negative_cases:
        assert not secretary._detect_negation(msg), f"不应检测到否定: {msg}"
    
    print("  ✓ 否定检测通过")


def test_failure_detection():
    """测试失败关键词检测"""
    print("\n" + "=" * 60)
    print("测试 3: 失败检测")
    
    secretary = Secretary()
    secretary.init("test_failure", state_dir="data/test")
    
    positive_cases = [
        "编译失败: Module not found",
        "Error: connection timeout",
        "部署失败，端口被占用",
        "我试了改端口还是不行",
        "build failed with exit code 1",
    ]
    
    for msg in positive_cases:
        assert secretary._detect_failure(msg), f"应检测到失败: {msg}"
    
    negative_cases = [
        "任务完成",
        "代码已提交",
        "测试全部通过",
        "部署成功",
    ]
    
    for msg in negative_cases:
        assert not secretary._detect_failure(msg), f"不应检测到失败: {msg}"
    
    print("  ✓ 失败检测通过")


def test_correction_triggers():
    """测试纠错触发逻辑"""
    print("\n" + "=" * 60)
    print("测试 4: 纠错触发")
    
    secretary = Secretary()
    secretary.init("test_correction", state_dir="data/test")
    
    # 模拟 3 次失败
    for i in range(3):
        secretary.record_turn(
            user_message="继续试试",
            role_response="Error: 又失败了",
            role_id="developer",
        )
    
    correction = secretary.check_correction()
    assert correction is not None, "3 次失败应触发纠错"
    assert "失败" in correction, "纠错提示应包含'失败'"
    print(f"  ✓ 失败纠错触发: {correction[:50]}...")
    
    # 重置状态
    secretary.init("test_correction2", state_dir="data/test")
    
    # 模拟 3 次用户否定
    for i in range(3):
        secretary.record_turn(
            user_message="不对，你搞错了",
            role_response="好的，我重新来",
            role_id="coach",
        )
    
    correction = secretary.check_correction()
    assert correction is not None, "3 次否定应触发纠错"
    assert "否定" in correction, "纠错提示应包含'否定'"
    print(f"  ✓ 否定纠错触发: {correction[:50]}...")
    
    # 重置状态
    secretary.init("test_correction3", state_dir="data/test")
    
    # 模拟 3 次失败 + 3 次否定
    for i in range(3):
        secretary.record_turn(
            user_message="不对，你又错了",
            role_response="Error: 部署失败",
            role_id="developer",
        )
    
    correction = secretary.check_correction()
    assert correction is not None, "失败+否定应触发最高级纠错"
    assert "最高级" in correction or "强制换人" in correction or "交接" in correction, "应是最高级纠错"
    print(f"  ✓ 最高级纠错触发: {correction[:50]}...")


def test_turn_recording():
    """测试轮次记录和状态更新"""
    print("\n" + "=" * 60)
    print("测试 5: 轮次记录")
    
    secretary = Secretary()
    secretary.init("test_turns", state_dir="data/test")
    
    # 正常对话 2 轮
    secretary.record_turn("你好", "你好！有什么可以帮你的？", "master")
    secretary.record_turn("帮我写个函数", "好的，我来写...", "developer")
    
    status = secretary.get_status()
    assert status["total_turns"] == 2
    assert status["consecutive_failures"] == 0
    assert status["user_negation_count"] == 0
    print(f"  ✓ 2 轮正常对话: {status}")
    
    # 1 轮失败
    secretary.record_turn("继续", "Error: 编译失败", "developer")
    status = secretary.get_status()
    assert status["total_turns"] == 3
    assert status["consecutive_failures"] == 1
    print(f"  ✓ 失败计数: consecutive_failures={status['consecutive_failures']}")
    
    # 1 轮成功后重置
    secretary.record_turn("好的", "编译成功！", "developer")
    status = secretary.get_status()
    assert status["consecutive_failures"] == 0, "成功后应重置失败计数"
    print(f"  ✓ 成功后重置: consecutive_failures={status['consecutive_failures']}")


def test_summary_trigger():
    """测试摘要触发条件"""
    print("\n" + "=" * 60)
    print("测试 6: 摘要触发条件")
    
    secretary = Secretary()
    secretary.init("test_summary", state_dir="data/test")
    
    # 少于 5 轮不应触发
    assert not secretary.should_summarize()
    print("  ✓ 0 轮: 不应触发摘要")
    
    # 模拟 5 轮
    for i in range(5):
        secretary.record_turn(f"消息{i}", f"回复{i}", "test")
    
    assert secretary.should_summarize()
    print("  ✓ 5 轮: 应触发摘要")
    
    # 模拟生成摘要后重置
    secretary._state.turns_since_last_summary = 0
    assert not secretary.should_summarize()
    print("  ✓ 摘要后重置: 不应触发")


def test_context_injection():
    """测试上下文注入"""
    print("\n" + "=" * 60)
    print("测试 7: 上下文注入")
    
    secretary = Secretary()
    secretary.init("test_context", state_dir="data/test")
    
    secretary.set_project("我的项目", "Phase 2")
    secretary.add_completed_module("Header")
    secretary.add_completed_module("NavBar")
    secretary.set_in_progress("TaskCard")
    
    context = secretary.get_context_injection()
    assert "我的项目" in context
    assert "Phase 2" in context
    assert "Header" in context
    print(f"  ✓ 上下文注入: {context[:100]}...")


def test_document_retrieval():
    """测试文档检索"""
    print("\n" + "=" * 60)
    print("测试 8: 文档检索")
    
    secretary = Secretary()
    secretary.init("test_docs", state_dir="data/test")
    
    # 设置不存在的文档
    result = secretary.get_document("PROJECT_PLAN")
    assert "未找到" in result
    print(f"  ✓ 缺失文档: {result}")
    
    secretary.set_project_docs(
        project_plan="nonexistent.md",
        status="nonexistent.md",
    )
    result = secretary.get_document("PROJECT_PLAN")
    assert "未找到" in result
    print("  ✓ 不存在的文件: 正确处理")


def run_all():
    print("\n" + "█" * 60)
    print("  秘书机制 (Secretary) 单元测试")
    print("█" * 60)
    
    test_runtime_state()
    test_negation_detection()
    test_failure_detection()
    test_correction_triggers()
    test_turn_recording()
    test_summary_trigger()
    test_context_injection()
    test_document_retrieval()
    
    print("\n" + "█" * 60)
    print("  全部测试通过 ✓")
    print("█" * 60)


if __name__ == "__main__":
    run_all()