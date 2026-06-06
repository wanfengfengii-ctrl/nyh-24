import sys
import requests
from datetime import date, timedelta

BASE_URL = "http://127.0.0.1:5001"

def test_system():
    session = requests.Session()
    errors = []
    passed = 0

    print("=" * 60)
    print("地下冰窖藏冰巡检系统 - 业务规则测试")
    print("=" * 60)

    # 1. 登录测试
    print("\n【1】登录测试")
    response = session.post(f"{BASE_URL}/login", data={
        "username": "admin",
        "password": "admin123"
    }, allow_redirects=False)
    if response.status_code == 302:
        print("  ✓ 登录成功")
        passed += 1
    else:
        print("  ✗ 登录失败")
        errors.append("登录失败")

    # 2. 冰窖编号不能重复
    print("\n【2】冰窖编号不能重复测试")
    # 先创建第一个冰窖
    response = session.post(f"{BASE_URL}/icehouses/new", data={
        "code": "TEST-001",
        "location": "测试位置1",
        "build_year": "1900",
        "capacity": "500",
        "is_open": "on"
    }, allow_redirects=False)
    if response.status_code == 302:
        print("  ✓ 第一个冰窖创建成功")
        passed += 1
    else:
        print("  ✗ 第一个冰窖创建失败")
        errors.append("第一个冰窖创建失败")

    # 尝试创建相同编号的冰窖
    response = session.post(f"{BASE_URL}/icehouses/new", data={
        "code": "TEST-001",
        "location": "测试位置2",
        "build_year": "1900",
        "capacity": "300"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 重复编号被正确拒绝")
        passed += 1
    else:
        print("  ✗ 重复编号未被拒绝")
        errors.append("冰窖编号重复校验失败")

    # 3. 入窖日期不能晚于当前日期
    print("\n【3】入窖日期不能晚于当前日期测试")
    future_date = (date.today() + timedelta(days=10)).isoformat()
    response = session.post(f"{BASE_URL}/batches/new", data={
        "ice_house_id": "1",
        "entry_date": future_date,
        "ice_count": "100",
        "expected_storage_period": "90",
        "current_remaining": "100"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 未来日期被正确拒绝")
        passed += 1
    else:
        print("  ✗ 未来日期未被拒绝")
        errors.append("入窖日期校验失败")

    # 4. 创建一个有效批次
    print("\n【4】创建有效批次")
    past_date = (date.today() - timedelta(days=5)).isoformat()
    response = session.post(f"{BASE_URL}/batches/new", data={
        "ice_house_id": "1",
        "entry_date": past_date,
        "ice_count": "200",
        "expected_storage_period": "90",
        "current_remaining": "200"
    }, allow_redirects=False)
    if response.status_code == 302:
        print("  ✓ 有效批次创建成功")
        passed += 1
    else:
        print("  ✗ 有效批次创建失败")
        errors.append("有效批次创建失败")

    # 5. 当前剩余量不能大于入窖数量
    print("\n【5】当前剩余量不能大于入窖数量测试")
    response = session.post(f"{BASE_URL}/batches/new", data={
        "ice_house_id": "1",
        "entry_date": past_date,
        "ice_count": "100",
        "expected_storage_period": "90",
        "current_remaining": "150"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 剩余量大于入窖量被正确拒绝")
        passed += 1
    else:
        print("  ✗ 剩余量大于入窖量未被拒绝")
        errors.append("剩余量校验失败")

    # 6. 巡检日期不能晚于当前日期
    print("\n【6】巡检日期不能晚于当前日期测试")
    response = session.post(f"{BASE_URL}/inspections/new", data={
        "ice_house_id": "1",
        "inspection_date": future_date,
        "temperature": "-5",
        "humidity": "60",
        "melt_level": "normal",
        "suggestions": "正常"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 未来巡检日期被正确拒绝")
        passed += 1
    else:
        print("  ✗ 未来巡检日期未被拒绝")
        errors.append("巡检日期校验失败")

    # 7. 创建正常巡检记录
    print("\n【7】创建正常巡检记录")
    response = session.post(f"{BASE_URL}/inspections/new", data={
        "ice_house_id": "1",
        "inspection_date": date.today().isoformat(),
        "temperature": "-4",
        "humidity": "65",
        "melt_level": "normal",
        "suggestions": "一切正常"
    }, allow_redirects=False)
    if response.status_code == 302:
        print("  ✓ 正常巡检记录创建成功")
        passed += 1
    else:
        print("  ✗ 正常巡检记录创建失败")
        errors.append("正常巡检记录创建失败")

    # 8. 渗水时自动标记高风险
    print("\n【8】渗水时自动标记高风险测试")
    response = session.post(f"{BASE_URL}/inspections/new", data={
        "ice_house_id": "1",
        "inspection_date": date.today().isoformat(),
        "temperature": "-2",
        "humidity": "80",
        "seepage": "on",
        "melt_level": "normal",
        "suggestions": "发现渗水"
    }, allow_redirects=False)
    if response.status_code == 302:
        # 检查冰窖是否标记为高风险
        detail_response = session.get(f"{BASE_URL}/icehouses/1")
        if "高风险" in detail_response.text:
            print("  ✓ 渗水后冰窖被正确标记为高风险")
            passed += 1
        else:
            print("  ✗ 渗水后冰窖未标记为高风险")
            errors.append("渗水高风险标记失败")
    else:
        print("  ✗ 渗水巡检记录创建失败")
        errors.append("渗水巡检记录创建失败")

    # 9. 严重融损时自动标记高风险
    print("\n【9】严重融损时自动标记高风险测试")
    # 先创建第二个冰窖
    session.post(f"{BASE_URL}/icehouses/new", data={
        "code": "TEST-002",
        "location": "测试位置2",
        "build_year": "1910",
        "capacity": "300"
    }, allow_redirects=False)
    response = session.post(f"{BASE_URL}/inspections/new", data={
        "ice_house_id": "2",
        "inspection_date": date.today().isoformat(),
        "temperature": "2",
        "humidity": "75",
        "melt_level": "severe",
        "suggestions": "严重融损"
    }, allow_redirects=False)
    if response.status_code == 302:
        detail_response = session.get(f"{BASE_URL}/icehouses/2")
        if "高风险" in detail_response.text:
            print("  ✓ 严重融损后冰窖被正确标记为高风险")
            passed += 1
        else:
            print("  ✗ 严重融损后冰窖未标记为高风险")
            errors.append("严重融损高风险标记失败")
    else:
        print("  ✗ 严重融损巡检记录创建失败")
        errors.append("严重融损巡检记录创建失败")

    # 10. 融损登记测试
    print("\n【10】融损登记测试")
    response = session.post(f"{BASE_URL}/melt-losses/new", data={
        "ice_house_id": "1",
        "batch_id": "1",
        "record_date": date.today().isoformat(),
        "loss_amount": "50",
        "reason": "温度波动"
    }, allow_redirects=False)
    if response.status_code == 302:
        print("  ✓ 融损登记成功")
        passed += 1
    else:
        print("  ✗ 融损登记失败")
        errors.append("融损登记失败")

    # 11. 融损数量不能大于剩余量
    print("\n【11】融损数量不能大于剩余量测试")
    response = session.post(f"{BASE_URL}/melt-losses/new", data={
        "ice_house_id": "1",
        "batch_id": "1",
        "record_date": date.today().isoformat(),
        "loss_amount": "1000",
        "reason": "测试"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 超量融损被正确拒绝")
        passed += 1
    else:
        print("  ✗ 超量融损未被拒绝")
        errors.append("融损数量校验失败")

    # 12. 修缮工单测试
    print("\n【12】修缮工单测试")
    response = session.post(f"{BASE_URL}/repairs/new", data={
        "ice_house_id": "1",
        "report_date": date.today().isoformat(),
        "issue_description": "窖体渗水需要修缮"
    }, allow_redirects=False)
    if response.status_code == 302:
        print("  ✓ 修缮工单创建成功")
        passed += 1
    else:
        print("  ✗ 修缮工单创建失败")
        errors.append("修缮工单创建失败")

    # 13. 未完成修缮的冰窖不能设置为开放状态
    print("\n【13】未完成修缮的冰窖不能设置开放状态测试")
    # 冰窖1当前是开放状态且有未完成修缮
    # 尝试保持开放状态应该被拒绝（因为已经有未完成修缮）
    # 我们尝试编辑冰窖，保持开放状态
    response = session.post(f"{BASE_URL}/icehouses/1/edit", data={
        "code": "TEST-001",
        "location": "测试位置1-更新",
        "build_year": "1900",
        "capacity": "500",
        "is_open": "on"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 未完成修缮时设置开放状态被正确拒绝")
        passed += 1
    else:
        print("  ✗ 未完成修缮时开放状态未被拒绝")
        errors.append("修缮状态校验失败")

    # 14. 报修日期不能晚于当前日期
    print("\n【14】报修日期不能晚于当前日期测试")
    response = session.post(f"{BASE_URL}/repairs/new", data={
        "ice_house_id": "1",
        "report_date": future_date,
        "issue_description": "测试"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 未来报修日期被正确拒绝")
        passed += 1
    else:
        print("  ✗ 未来报修日期未被拒绝")
        errors.append("报修日期校验失败")

    # 15. 首页概览测试
    print("\n【15】首页概览测试")
    response = session.get(f"{BASE_URL}/")
    if "冰窖总数" in response.text and "高风险" in response.text:
        print("  ✓ 首页概览正常显示统计数据")
        passed += 1
    else:
        print("  ✗ 首页概览显示异常")
        errors.append("首页概览显示异常")

    # 16. 融损登记 - 批次必须属于所选冰窖
    print("\n【16】融损登记-批次不属于所选冰窖测试")
    # 先给冰窖2也创建一个批次
    session.post(f"{BASE_URL}/batches/new", data={
        "ice_house_id": "2",
        "entry_date": past_date,
        "ice_count": "150",
        "expected_storage_period": "60",
        "current_remaining": "150"
    }, allow_redirects=False)
    # 选择冰窖1，但提交冰窖2的批次
    response = session.post(f"{BASE_URL}/melt-losses/new", data={
        "ice_house_id": "1",
        "batch_id": "2",
        "record_date": date.today().isoformat(),
        "loss_amount": "10",
        "reason": "测试跨冰窖测试"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 跨冰窖批次融损被正确拒绝")
        passed += 1
    else:
        print("  ✗ 跨冰窖批次融损未被拒绝")
        errors.append("融损登记-批次所属冰窖校验失败")

    # 17. 修缮工单 - 修缮日期不能晚于当前日期
    print("\n【17】修缮工单-修缮日期不能晚于当前日期测试")
    response = session.post(f"{BASE_URL}/repairs/1/edit", data={
        "ice_house_id": "1",
        "report_date": date.today().isoformat(),
        "issue_description": "窖体渗水需要修缮",
        "status": "in_progress",
        "repair_date": future_date,
        "repair_cost": "500",
        "notes": "测试"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 未来修缮日期被正确拒绝")
        passed += 1
    else:
        print("  ✗ 未来修缮日期未被拒绝")
        errors.append("修缮日期校验失败")

    # 18. 藏冰批次 - 当前剩余量不能为负数
    print("\n【18】藏冰批次-当前剩余量不能为负数测试")
    response = session.post(f"{BASE_URL}/batches/1/edit", data={
        "ice_house_id": "1",
        "entry_date": past_date,
        "ice_count": "200",
        "expected_storage_period": "90",
        "current_remaining": "-10"
    }, allow_redirects=False)
    if response.status_code == 200:
        print("  ✓ 负数剩余量被正确拒绝")
        passed += 1
    else:
        print("  ✗ 负数剩余量未被拒绝")
        errors.append("剩余量负数校验失败")

    # 结果汇总
    print("\n" + "=" * 60)
    print(f"测试结果：{passed} 项通过，{len(errors)} 项失败")
    print("=" * 60)

    if errors:
        print("\n失败项：")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}")
        return 1
    else:
        print("\n🎉 所有测试通过！")
        return 0

if __name__ == "__main__":
    sys.exit(test_system())
