"""逐次模型响应后的可观测 token 预算；不猜测服务商未返回的用量。"""


def budget_status(total_tokens, usage_complete, limit):
    if limit is None:
        return None
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError('token 预算必须为正整数')
    if not usage_complete:
        return 'usage_unavailable'
    if total_tokens >= limit:
        return 'token_budget'
    return None
