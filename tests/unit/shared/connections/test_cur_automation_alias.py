from app.shared.adapters.aws_cur import AWSCURAdapter
from app.shared.connections.cur_automation import IAMCURManager


def test_cur_automation_alias_points_to_cur_adapter() -> None:
    assert IAMCURManager is AWSCURAdapter
