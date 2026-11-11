"""有限的高风险请求回退和引用来源检查；不能替代事实核验。"""
import json
import re
import unicodedata

ID = re.compile(r'(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])', re.I)
DIRECT_MEDICAL = re.compile(r'用药|服药|药物剂量|药品剂量|药量|拆线|补碘|辅酶\s*q\s*10|(孕妇|怀孕|孕期).{0,8}缺碘|前列腺.{0,6}(偏大|增生|肥大)|白醋.{0,6}(去斑|祛斑)', re.I)
MEDICAL_ACTION = re.compile(r'(药|药物|药品|处方|针剂).{0,12}(剂量|用量|服用|怎么吃|吃多少|吃几片|吃几粒|每天几次|注射)|(剂量|用量|服用|怎么吃|吃多少|吃几片|吃几粒|每天几次|注射).{0,12}(药|药物|药品|处方|针剂)')
SENSITIVE_PERSON = re.compile(r'孕妇|怀孕|孕期|哺乳期')
PERSON_HEALTH = re.compile(r'疥疮|生病|疾病|用药|药|治疗|检查|健康|饮食|水果|吃|营养|缺|疼|痛|怎么办|过敏|皮疹|血压|血糖|胎动|出血')
CHILD = re.compile(r'婴儿|宝宝|幼儿|儿童|小孩|孩子')
CHILD_HEALTH = re.compile(r'奶粉|喂养|饮食|营养|吃什么|长高|补充|生病|治疗|药|发烧|咳嗽|过敏|哭闹|发育|眼睛')
FORMULA = re.compile(r'(奶粉|配方奶).{0,8}(过稀|冲调|怎么冲|比例)')
TREATMENT = re.compile(r'(中药|药物|药品|偏方|草药|处方).{0,15}(治疗|治愈|治|服|吃|用)|(治疗|治愈|治).{0,15}(中药|药物|药品|偏方|草药|处方)')
FUEL_REPAIR = re.compile(r'(柴油|汽油|燃油).{0,12}(结蜡|混加|添加|加热|维修|怎么办)|(结蜡|混加|添加|加热|维修).{0,12}(柴油|汽油|燃油)')


def risk_category(question, history=None):
    context = unicodedata.normalize('NFKC', question)
    if history and re.search(r'剂量|用量|多少|怎么吃|怎么用|服用|多久|怎么办|可以吗', context):
        previous = [str(m.get('content') or '') for m in history if m.get('role') == 'user'][-2:]
        context = unicodedata.normalize('NFKC', ' '.join(previous + [context]))
    context = re.sub(r'\s+', '', context)
    if FUEL_REPAIR.search(context):
        return 'physical_safety_scope'
    if (DIRECT_MEDICAL.search(context) or MEDICAL_ACTION.search(context) or TREATMENT.search(context)
            or (SENSITIVE_PERSON.search(context) and PERSON_HEALTH.search(context))
            or FORMULA.search(context) or (CHILD.search(context) and CHILD_HEALTH.search(context))):
        return 'medical_scope'
    return None


def guardrail_fallback(question, history=None):
    category = risk_category(question, history)
    if category == 'physical_safety_scope':
        return category, ('现有网页资料未经核验，无法安全确认燃油混加或维修的具体操作。'
                          '请先确保人车处于安全位置，联系车辆厂家或专业救援，按车辆说明处理。')
    if category == 'medical_scope':
        return category, ('当前资料来源未经医学核验，无法安全确定具体用药、剂量、喂养或处理方法。'
                          '请联系医生或药师，结合具体情况和正规产品说明确认；不要自行依据网页操作。')
    return None, None


def medical_fallback(question, history=None):
    """对明确触发的医疗操作问题不复述未核验网页的具体操作。"""
    category, answer = guardrail_fallback(question, history)
    return answer if category == 'medical_scope' else None


def evidence_notice(calls):
    """仅报告可验证的元数据缺失；相似度和重排分数不表示可信度。"""
    searches = [c for c in calls if c.get('name') == 'search_docs' and c.get('success')]
    if not searches:
        return None
    for call in searches:
        try:
            docs = json.loads(call.get('result', ''))
        except (TypeError, ValueError):
            continue
        if isinstance(docs, list) and docs:
            return '证据状态：检索段落未提供可验证的原始来源和发布日期；相关性分数不能证明事实或时效。'
    return None


def citation_notice(answer, calls):
    """只检查完整 ID 是否来自本次成功搜索；不检查语义或事实。"""
    if not answer:
        return None
    searches = [c for c in calls if c.get('name') == 'search_docs' and c.get('success')]
    if not searches:
        return None
    valid = set()
    for call in searches:
        try:
            docs = json.loads(call.get('result', ''))
            if not isinstance(docs, list):
                continue
            for doc in docs:
                if isinstance(doc, dict):
                    valid.update(x.lower() for x in ID.findall(str(doc.get('source', ''))))
        except (TypeError, ValueError):
            continue
    mentioned = {x.lower() for x in ID.findall(answer)}
    # 若回答引用了本轮实际获得的网页链接，不强制它同时引用无关的本地段落。
    web_urls = set()
    for call in calls:
        if not call.get('success'):
            continue
        try:
            if call.get('name') == 'web_fetch':
                url = json.loads(call.get('arguments', '{}')).get('url')
                if isinstance(url, str):
                    web_urls.add(url)
            elif call.get('name') == 'web_search':
                data = json.loads(call.get('result', '{}'))
                web_urls.update(item.get('url', '') for item in data.get('results', []) if isinstance(item, dict))
        except (TypeError, ValueError, AttributeError):
            continue
    cited_web = any(url and url in answer for url in web_urls)
    if mentioned - valid:
        return '引用检查：回答包含未在本轮成功检索结果中找到的段落 ID，请核对来源。'
    if not mentioned and cited_web:
        return None
    if not valid:
        return '证据检查：本轮搜索未返回可识别的段落 ID；这不代表整个语料库不存在相关资料。'
    if not mentioned:
        return '引用检查：回答未包含可识别的完整段落 ID，请核对来源。'
    return None
