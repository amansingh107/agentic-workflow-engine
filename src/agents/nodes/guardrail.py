import ast
from typing import Dict, Any, List, Tuple
from ..state import AgentState


class SecurityASTVisitor(ast.NodeVisitor):
    """AST Visitor that detects dangerous Python operations and system-level exploits."""

    DANGEROUS_MODULES = {
        "os": "System OS manipulation",
        "subprocess": "Process execution / shell invocation",
        "shutil": "Filesystem manipulation / tree deletion",
        "socket": "Direct network socket creation",
        "ctypes": "Low-level memory / C library access",
        "pty": "Pseudo-terminal allocation",
        "sys": "Interpreter modification",
    }

    DANGEROUS_FUNCTIONS = {
        "eval": "Dynamic code evaluation",
        "exec": "Dynamic code execution",
        "compile": "Dynamic compilation",
        "__import__": "Dynamic module import",
    }

    def __init__(self):
        self.risks: List[Tuple[str, str]] = []  # (severity, description)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_module = alias.name.split(".")[0]
            if base_module in self.DANGEROUS_MODULES:
                self.risks.append(("HIGH", f"Imported dangerous module: '{alias.name}' ({self.DANGEROUS_MODULES[base_module]})"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_module = node.module.split(".")[0]
            if base_module in self.DANGEROUS_MODULES:
                self.risks.append(("HIGH", f"Imported from dangerous module: '{node.module}' ({self.DANGEROUS_MODULES[base_module]})"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect eval(), exec(), etc.
        if isinstance(node.func, ast.Name):
            if node.func.id in self.DANGEROUS_FUNCTIONS:
                self.risks.append(("CRITICAL", f"Invoked dangerous built-in: '{node.func.id}()'"))
        
        # Detect os.system(), os.remove(), etc.
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                module_name = node.func.value.id
                func_name = node.func.attr
                if module_name == "os" and func_name in ["system", "popen", "remove", "unlink", "rmdir"]:
                    self.risks.append(("CRITICAL", f"Invoked dangerous OS function: '{module_name}.{func_name}()'"))
                elif module_name == "subprocess":
                    self.risks.append(("CRITICAL", f"Invoked subprocess function: '{module_name}.{func_name}()'"))
                elif module_name == "shutil" and func_name in ["rmtree", "move"]:
                    self.risks.append(("CRITICAL", f"Invoked destructive filesystem call: '{module_name}.{func_name}()'"))

        self.generic_visit(node)


def analyze_code_safety(code: str) -> Tuple[float, List[str]]:
    """
    Statically analyzes code using AST parser to calculate a risk score (0.0 to 1.0)
    and list of detected security concerns.
    """
    if not code or not code.strip():
        return 0.0, []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return 0.8, [f"Syntax error during AST inspection: {e.msg} at line {e.lineno}"]

    visitor = SecurityASTVisitor()
    visitor.visit(tree)

    reasons = [desc for _, desc in visitor.risks]
    has_critical = any(sev == "CRITICAL" for sev, _ in visitor.risks)
    has_high = any(sev == "HIGH" for sev, _ in visitor.risks)

    if has_critical:
        risk_score = 0.95
    elif has_high:
        risk_score = 0.70
    elif reasons:
        risk_score = 0.40
    else:
        risk_score = 0.05

    return risk_score, reasons


def guardrail_node(state: AgentState) -> Dict[str, Any]:
    """
    Guardrail Agent Node:
    Analyzes generated Python code for security hazards, calculates risk score,
    and flags whether Human-in-the-Loop approval is required.
    """
    code = state.get("code", "")
    risk_score, reasons = analyze_code_safety(code)

    # If risk is elevated (>= 0.6) or if it's explicitly flagged
    requires_approval = risk_score >= 0.6

    return {
        "risk_score": risk_score,
        "risk_reasons": reasons,
        "requires_approval": requires_approval,
        "status": "awaiting_approval" if requires_approval else "guardrail_approved"
    }
