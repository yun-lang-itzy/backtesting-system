from ashare import Strategy

class UserStrategy(Strategy):
    def on_close(self, context):
        return {}  # 空仓，用于检查系统；返回 None 表示继续持有。
