"""仅计算数字和基本算术，不执行任意 Python 代码。"""
import ast
import operator

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Mod: operator.mod}


def run(expression):
    if len(expression) > 200:
        raise ValueError("表达式过长")
    def calculate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](calculate(node.left), calculate(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = calculate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError("仅支持数字、括号和 + - * / %")
    return str(calculate(ast.parse(expression, mode="eval").body))
