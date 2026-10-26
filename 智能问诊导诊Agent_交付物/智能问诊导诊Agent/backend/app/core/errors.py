"""统一业务错误：接口回调 `{code,message,data}`，code 非 0 表示失败。"""


class ApiError(Exception):
    def __init__(self, code: int, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status


# —— 统一错误码 ——
# 通用
PARAM_ERROR = 4000          # 参数非法
AUTH_FAILED = 4001          # 认证失败(密码错误/token无效)
DUPLICATE = 4002            # 资源重复(账号已存在)
UNAUTHORIZED = 4003         # 未登录
FORBIDDEN = 4004            # 越权/无权限
NOT_FOUND = 4005            # 不存在(会话/报告)
CONFLICT = 4006             # 状态冲突(如报告未生成)
INPUT_BLOCKED = 4007        # 输入被内容安全拦截(注入/超长)
LLM_ERROR = 5001            # 大模型调用失败
DB_ERROR = 5002             # 数据库错误
RATE_LIMITED = 4008         # 触发限流
WAIT_FOR_SLOTS = 4009       # 追问未完成，报告尚不可生成