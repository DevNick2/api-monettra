"""
ia_tools.py — Catálogo de tools do IA Engine (shared layer).

Posicionado no shared layer para permitir reutilização por outros módulos
sem criar dependências circulares entre domínios.

Responsável por:
  - Declarar as tools expostas ao OpenRouter (com label amigável)
  - Executar tools com base nos Services já existentes
  - Sanitizar resultados antes de repassar ao modelo e ao frontend
"""

from __future__ import annotations

from fastapi import HTTPException

from src.modules.analytics.analytics_service import AnalyticsService
from src.modules.categories.categories_service import CategoriesService
from src.modules.categories.dtos import CategoryResponse, CreateCategoryDTO
from src.modules.subscriptions.dtos import (
    CreateSubscriptionDTO,
    SubscriptionResponse,
)
from src.modules.subscriptions.subscriptions_service import SubscriptionsService
from src.modules.transactions.dtos import CreateTransactionDTO, TransactionResponse
from src.modules.transactions.transactions_service import TransactionsService


class IaToolRegistry:
    def __init__(
        self,
        transactions_service: TransactionsService,
        categories_service: CategoriesService,
        subscriptions_service: SubscriptionsService,
        analytics_service: AnalyticsService,
    ):
        self.transactions_service = transactions_service
        self.categories_service = categories_service
        self.subscriptions_service = subscriptions_service
        self.analytics_service = analytics_service

    # ------------------------------------------------------------------
    # Definições das Tools (enviadas ao OpenRouter)
    # ------------------------------------------------------------------
    def get_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_user_transactions",
                    "label": "Consultando teus registros...",
                    "description": (
                        "Lista transações financeiras do usuário com filtros "
                        "opcionais por mês, ano, categoria e status de pagamento."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "month": {"type": ["integer", "null"], "minimum": 1, "maximum": 12},
                            "year": {"type": ["integer", "null"]},
                            "category_code": {"type": ["string", "null"]},
                            "is_paid": {"type": ["boolean", "null"]},
                            "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 50},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_financial_summary",
                    "label": "Somando teus movimentos...",
                    "description": (
                        "Retorna um resumo financeiro do período com totais de "
                        "receitas, despesas, saldo e distribuição por categorias."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "month": {"type": ["integer", "null"], "minimum": 1, "maximum": 12},
                            "year": {"type": ["integer", "null"]},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_categories",
                    "label": "Consultando tuas categorias...",
                    "description": (
                        "Lista as categorias financeiras disponíveis para o usuário, "
                        "opcionalmente filtradas por tipo."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": ["string", "null"],
                                "enum": ["income", "expense", None],
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_subscriptions",
                    "label": "Revisando tuas assinaturas...",
                    "description": (
                        "Lista assinaturas cadastradas, podendo filtrar apenas as ativas."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active_only": {"type": ["boolean", "null"]},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_transaction",
                    "label": "Registrando tua transação...",
                    "description": "Cria uma nova transação financeira para o usuário.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "amount": {"type": ["string", "integer", "number"]},
                            "type": {"type": "string", "enum": ["income", "expense"]},
                            "due_date": {
                                "type": "string",
                                "description": "Data no formato DD/MM/YYYY",
                            },
                            "category_code": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                            "is_paid": {"type": ["boolean", "null"]},
                        },
                        "required": ["title", "amount", "type", "due_date"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_subscription",
                    "label": "Registrando tua assinatura...",
                    "description": "Cria uma nova assinatura recorrente para o usuário.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string"},
                            "amount": {"type": ["string", "integer", "number"]},
                            "recurrence": {
                                "type": "string",
                                "enum": [
                                    "monthly",
                                    "yearly",
                                    "biannual",
                                    "quarterly",
                                    "semiannual",
                                ],
                            },
                            "billing_date": {
                                "type": ["string", "null"],
                                "description": "Data no formato DD/MM/YYYY",
                            },
                            "has_trial": {"type": ["boolean", "null"]},
                            "is_active": {"type": ["boolean", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                        "required": ["provider", "amount", "recurrence"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_category",
                    "label": "Criando uma nova categoria...",
                    "description": "Cria uma nova categoria financeira para o usuário.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "color": {"type": "string"},
                            "icon_name": {"type": "string"},
                            "type": {"type": "string", "enum": ["income", "expense"]},
                        },
                        "required": ["title", "color", "icon_name", "type"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def get_label(self, tool_name: str) -> str | None:
        """Retorna o label amigável de uma tool pelo nome."""
        for tool_def in self.get_definitions():
            fn = tool_def.get("function", {})
            if fn.get("name") == tool_name:
                return fn.get("label")
        return None

    # ------------------------------------------------------------------
    # Execução de Tools
    # ------------------------------------------------------------------
    def execute(
        self,
        tool_name: str,
        arguments: dict,
        user_id: int,
        account_id: int,
    ) -> dict:
        executor = getattr(self, f"_execute_{tool_name}", None)
        if not executor:
            raise HTTPException(status_code=400, detail=f"Tool '{tool_name}' não suportada")

        try:
            return executor(arguments, user_id, account_id)
        except Exception as e:
            self.transactions_service.repository.session.rollback()
            raise e

    def _execute_get_user_transactions(
        self,
        arguments: dict,
        _user_id: int,
        account_id: int,
    ) -> dict:
        month = arguments.get("month")
        year = arguments.get("year")
        category_code = arguments.get("category_code")
        is_paid = arguments.get("is_paid")
        limit = arguments.get("limit") or 10

        records = self.transactions_service.find_all(account_id, month=month, year=year)
        serialized = [self._serialize_transaction(record) for record in records]

        if category_code:
            serialized = [
                item for item in serialized
                if item.get("category_code") == str(category_code)
            ]
        if is_paid is not None:
            serialized = [
                item for item in serialized if item.get("is_paid") is bool(is_paid)
            ]

        limited = serialized[:limit]
        return {
            "tool_name": "get_user_transactions",
            "tool_label": "Consultando teus registros...",
            "result_text": (
                f"Encontrei {len(serialized)} transações no filtro solicitado. "
                f"Exibindo {len(limited)} item(ns)."
            ),
            "result_for_model": {
                "count": len(serialized),
                "transactions": limited,
            },
        }

    def _execute_get_financial_summary(
        self,
        arguments: dict,
        _user_id: int,
        account_id: int,
    ) -> dict:
        month = arguments.get("month")
        year = arguments.get("year")
        records = self.transactions_service.find_all(account_id, month=month, year=year)
        serialized = [self._serialize_transaction(record) for record in records]

        income_cents = 0
        expense_cents = 0
        categories: dict[str, int] = {}

        for item in serialized:
            amount_cents = item["amount_cents"]
            if item["type"] == "income":
                income_cents += amount_cents
            else:
                expense_cents += amount_cents
                category_name = item.get("category", {}).get("title") or "Sem categoria"
                categories[category_name] = categories.get(category_name, 0) + amount_cents

        top_categories = sorted(
            (
                {"name": name, "total": self._format_currency(total), "total_cents": total}
                for name, total in categories.items()
            ),
            key=lambda item: item["total_cents"],
            reverse=True,
        )[:5]

        summary = {
            "income": self._format_currency(income_cents),
            "expense": self._format_currency(expense_cents),
            "balance": self._format_currency(income_cents - expense_cents),
            "income_cents": income_cents,
            "expense_cents": expense_cents,
            "balance_cents": income_cents - expense_cents,
            "transaction_count": len(serialized),
            "top_categories": top_categories,
            "month": month,
            "year": year,
        }

        return {
            "tool_name": "get_financial_summary",
            "tool_label": "Somando teus movimentos...",
            "result_text": (
                f"Resumo calculado com {len(serialized)} transações. "
                f"Receitas: {summary['income']}, despesas: {summary['expense']}."
            ),
            "result_for_model": summary,
            "ui_block": {
                "type": "financial-summary",
                "title": "Resumo financeiro",
                "summary": summary,
            },
        }

    def _execute_list_categories(
        self,
        arguments: dict,
        _user_id: int,
        account_id: int,
    ) -> dict:
        category_type = arguments.get("type")
        categories = self.categories_service.find_all(account_id)
        serialized = [
            CategoryResponse.model_validate(category).model_dump(mode="json")
            for category in categories
        ]
        if category_type:
            serialized = [
                item for item in serialized if item.get("type") == category_type
            ]

        return {
            "tool_name": "list_categories",
            "tool_label": "Consultando tuas categorias...",
            "result_text": f"Localizei {len(serialized)} categorias disponíveis.",
            "result_for_model": {"categories": serialized, "count": len(serialized)},
            "ui_block": {
                "type": "categories-list",
                "title": "Categorias disponíveis",
                "items": serialized[:12],
                "count": len(serialized),
            },
        }

    def _execute_get_subscriptions(
        self,
        arguments: dict,
        _user_id: int,
        account_id: int,
    ) -> dict:
        active_only = bool(arguments.get("active_only"))
        records = (
            self.subscriptions_service.find_active(account_id)
            if active_only
            else self.subscriptions_service.find_all(account_id)
        )
        serialized = [
            SubscriptionResponse.model_validate(record).model_dump(mode="json")
            for record in records
        ]
        return {
            "tool_name": "get_subscriptions",
            "tool_label": "Revisando tuas assinaturas...",
            "result_text": f"Encontrei {len(serialized)} assinatura(s).",
            "result_for_model": {
                "subscriptions": serialized,
                "count": len(serialized),
                "active_only": active_only,
            },
            "ui_block": {
                "type": "subscriptions-list",
                "title": "Assinaturas",
                "items": serialized[:10],
                "count": len(serialized),
            },
        }

    def _execute_create_transaction(
        self,
        arguments: dict,
        user_id: int,
        account_id: int,
    ) -> dict:
        payload = CreateTransactionDTO(**arguments)
        record = self.transactions_service.create(user_id, account_id, payload)
        serialized = TransactionResponse.model_validate(record).model_dump(mode="json")
        return {
            "tool_name": "create_transaction",
            "tool_label": "Registrando tua transação...",
            "result_text": (
                f"Transação '{serialized['title']}' criada com sucesso "
                f"para {serialized['due_date']}."
            ),
            "result_for_model": {"transaction": serialized, "created": True},
            "ui_block": {
                "type": "action-confirmation",
                "title": "Transação criada",
                "description": (
                    f"{serialized['title']} • {serialized['amount']} • "
                    f"{serialized['due_date']}"
                ),
                "entity_code": serialized["code"],
            },
        }

    def _execute_create_subscription(
        self,
        arguments: dict,
        user_id: int,
        account_id: int,
    ) -> dict:
        payload = CreateSubscriptionDTO(**arguments)
        record = self.subscriptions_service.create(user_id, account_id, payload)
        serialized = SubscriptionResponse.model_validate(record).model_dump(mode="json")
        return {
            "tool_name": "create_subscription",
            "tool_label": "Registrando tua assinatura...",
            "result_text": f"Assinatura '{serialized['provider']}' criada com sucesso.",
            "result_for_model": {"subscription": serialized, "created": True},
            "ui_block": {
                "type": "action-confirmation",
                "title": "Assinatura criada",
                "description": (
                    f"{serialized['provider']} • {serialized['amount']} • "
                    f"{serialized['recurrence']}"
                ),
                "entity_code": serialized["code"],
            },
        }

    def _execute_create_category(
        self,
        arguments: dict,
        user_id: int,
        account_id: int,
    ) -> dict:
        payload = CreateCategoryDTO(**arguments)
        record = self.categories_service.create(user_id, account_id, payload)
        serialized = CategoryResponse.model_validate(record).model_dump(mode="json")
        return {
            "tool_name": "create_category",
            "tool_label": "Criando uma nova categoria...",
            "result_text": f"Categoria '{serialized['title']}' criada com sucesso.",
            "result_for_model": {"category": serialized, "created": True},
            "ui_block": {
                "type": "action-confirmation",
                "title": "Categoria criada",
                "description": f"{serialized['title']} • {serialized['type']}",
                "entity_code": serialized["code"],
            },
        }

    def _serialize_transaction(self, record) -> dict:
        serialized = TransactionResponse.model_validate(record).model_dump(mode="json")
        amount_parts = str(serialized["amount"]).replace(".", "").split(",")
        amount_cents = (
            int(amount_parts[0]) * 100 + int(amount_parts[1])
            if len(amount_parts) == 2
            else 0
        )
        serialized["amount_cents"] = amount_cents
        serialized["category_code"] = (
            serialized.get("category", {}).get("code")
            if serialized.get("category")
            else None
        )
        return serialized

    @staticmethod
    def _format_currency(value_cents: int) -> str:
        sign = "-" if value_cents < 0 else ""
        cents = abs(value_cents)
        reais = cents // 100
        centavos = cents % 100
        reais_str = f"{reais:,}".replace(",", ".")
        return f"{sign}{reais_str},{centavos:02d}"
