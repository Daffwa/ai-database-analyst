"""Versioned clarification and non-overclarification cases for Tahap 5."""

from __future__ import annotations

from dataclasses import dataclass

SEMANTIC_EVALUATION_VERSION = "stage-5-v1"


@dataclass(frozen=True, slots=True)
class SemanticEvaluationCase:
    """One question and its deterministic clarification expectation."""

    case_id: str
    question: str
    expected_clarification: bool
    expected_rule_id: str | None = None


AMBIGUOUS_SEMANTIC_CASES: tuple[SemanticEvaluationCase, ...] = (
    SemanticEvaluationCase("AMB-001", "Siapa pelanggan terbaik?", True, "best_customer_measure"),
    SemanticEvaluationCase("AMB-002", "Who is the best customer?", True, "best_customer_measure"),
    SemanticEvaluationCase("AMB-003", "Berapa pelanggan aktif?", True, "active_customer_basis"),
    SemanticEvaluationCase("AMB-004", "How many active customers?", True, "active_customer_basis"),
    SemanticEvaluationCase("AMB-005", "Apa produk terbaik?", True, "best_product_measure"),
    SemanticEvaluationCase("AMB-006", "What is the best product?", True, "best_product_measure"),
    SemanticEvaluationCase("AMB-007", "Berapa pendapatan terbaru?", True, "latest_revenue_period"),
    SemanticEvaluationCase("AMB-008", "What is the latest revenue?", True, "latest_revenue_period"),
    SemanticEvaluationCase("AMB-009", "Apa penjualan terbesar?", True, "largest_sales_measure"),
    SemanticEvaluationCase("AMB-010", "What are the largest sales?", True, "largest_sales_measure"),
)

RESOLVED_SEMANTIC_CASES: tuple[SemanticEvaluationCase, ...] = (
    SemanticEvaluationCase(
        "CLR-001",
        "Siapa pelanggan terbaik berdasarkan total belanja?",
        False,
    ),
    SemanticEvaluationCase("CLR-002", "Who is the best customer by total spend?", False),
    SemanticEvaluationCase(
        "CLR-003",
        "Berapa pelanggan aktif yang pernah bertransaksi?",
        False,
    ),
    SemanticEvaluationCase("CLR-004", "How many active customers ever transacted?", False),
    SemanticEvaluationCase("CLR-005", "Apa produk terbaik berdasarkan unit terjual?", False),
    SemanticEvaluationCase("CLR-006", "What is the best product by units sold?", False),
    SemanticEvaluationCase("CLR-007", "Berapa pendapatan untuk bulan terbaru?", False),
    SemanticEvaluationCase("CLR-008", "What is the revenue for the latest month?", False),
    SemanticEvaluationCase("CLR-009", "Apa penjualan terbesar berdasarkan nilai?", False),
    SemanticEvaluationCase("CLR-010", "What are the largest sales by value?", False),
)
