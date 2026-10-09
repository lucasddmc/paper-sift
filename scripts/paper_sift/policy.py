"""Policy expressions over Jev facts and paper metadata.

Parsed with `ast` against a whitelist and evaluated by walking the tree; nothing reaches eval().
A bare fact name means "probability >= tau"; `p.<fact>` is the probability itself; `importance`,
`year` and `citations` are paper metadata. Missing facts count as probability 0.
"""
import ast

VARIABLES = ("importance", "year", "citations")

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b if b else 0.0}
_CMP = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


class PolicyError(ValueError):
    pass


class Expr:
    def __init__(self, source, facts):
        self.source, self.facts = source, frozenset(facts)
        try:
            self.tree = ast.parse(source, mode="eval").body
        except SyntaxError as e:
            raise PolicyError(f"cannot parse {source!r}: {e.msg}") from None
        self._check(self.tree)

    def __call__(self, record, tau):
        return self._eval(self.tree, record, tau)

    def _check(self, node):
        if isinstance(node, ast.BoolOp):
            children = node.values
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub)):
            children = [node.operand]
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            children = [node.left, node.right]
        elif isinstance(node, ast.Compare) and all(type(op) in _CMP for op in node.ops):
            children = [node.left, *node.comparators]
        elif isinstance(node, ast.Constant) and type(node.value) in (bool, int, float):
            children = []
        elif isinstance(node, ast.Name) and (node.id in self.facts or node.id in VARIABLES):
            children = []
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
              and node.value.id == "p" and node.attr in self.facts):
            children = []
        else:
            raise PolicyError(f"{ast.unparse(node)!r} is not allowed in {self.source!r}")
        for child in children:
            self._check(child)

    def _eval(self, node, r, tau):
        if isinstance(node, ast.BoolOp):
            values = (self._eval(v, r, tau) for v in node.values)
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand, r, tau)
            return (not value) if isinstance(node.op, ast.Not) else -value
        if isinstance(node, ast.BinOp):
            return _BIN[type(node.op)](float(self._eval(node.left, r, tau)), float(self._eval(node.right, r, tau)))
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, r, tau)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, r, tau)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            value = float(r.get(node.id) or 0.0)
            return value >= tau if node.id in self.facts else value
        return float(r.get(node.attr) or 0.0)  # p.<fact>
