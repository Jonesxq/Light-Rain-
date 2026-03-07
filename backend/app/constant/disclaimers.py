"""安全与合规免责声明模板"""

DISCLAIMER_TEMPLATES = {
    "medical": {
        "code": "medical",
        "title": "医疗提示",
        "body": "以下内容仅供参考，不能替代医生的专业诊断或治疗建议。如有不适或紧急情况，请及时就医。",
        "severity": "warning",
    },
    "legal": {
        "code": "legal",
        "title": "法律提示",
        "body": "以下内容仅供一般信息参考，不构成法律意见。具体问题请咨询具备资质的律师。",
        "severity": "warning",
    },
    "financial": {
        "code": "financial",
        "title": "金融提示",
        "body": "以下内容不构成投资建议或保证收益。市场有风险，投资需谨慎。",
        "severity": "warning",
    },
}


def normalize_labels(labels: list[str] | None) -> list[str]:
    """将标签规范化为允许的免责声明代码"""
    if not labels:
        return []
    allowed = set(DISCLAIMER_TEMPLATES.keys())
    seen = []
    for label in labels:
        code = (label or "").strip().lower()
        if not code or code not in allowed:
            continue
        if code in seen:
            continue
        seen.append(code)
    return seen


def build_disclaimers(labels: list[str] | None) -> list[dict]:
    """根据标签构建免责声明数据"""
    codes = normalize_labels(labels)
    return [DISCLAIMER_TEMPLATES[code] for code in codes if code in DISCLAIMER_TEMPLATES]


def get_disclaimer_map() -> dict:
    """获取免责声明模板映射"""
    return DISCLAIMER_TEMPLATES
