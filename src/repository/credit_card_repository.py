from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.schemas.credit_cards import CreditCardSchema, InvoiceSchema


class CreditCardRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    # ─── Credit Cards ──────────────────────────────────────────────────────────

    def find_all_by_account(self, account_id: int) -> list[CreditCardSchema]:
        return (
            self.session.execute(
                select(CreditCardSchema)
                .where(
                    CreditCardSchema.account_id == account_id,
                    CreditCardSchema.deleted_at == None,  # noqa: E711
                )
                .order_by(CreditCardSchema.name)
            )
            .scalars()
            .all()
        )

    def find_by_code(self, code: UUID, account_id: int) -> CreditCardSchema | None:
        return self.session.execute(
            select(CreditCardSchema).where(
                CreditCardSchema.code == code,
                CreditCardSchema.account_id == account_id,
                CreditCardSchema.deleted_at == None,  # noqa: E711
            )
        ).scalar_one_or_none()

    def find_by_id(self, card_id: int) -> CreditCardSchema | None:
        return self.session.get(CreditCardSchema, card_id)

    def create(self, data: dict) -> CreditCardSchema:
        card = CreditCardSchema(**data)
        self.session.add(card)
        self.session.commit()
        self.session.refresh(card)
        return card

    def update(self, card: CreditCardSchema) -> CreditCardSchema:
        self.session.commit()
        self.session.refresh(card)
        return card

    def soft_delete(self, card: CreditCardSchema) -> None:
        from datetime import datetime
        card.deleted_at = datetime.utcnow()
        self.session.commit()

    # ─── Invoices ──────────────────────────────────────────────────────────────

    def find_invoice(
        self, credit_card_id: int, month: int, year: int
    ) -> InvoiceSchema | None:
        return self.session.execute(
            select(InvoiceSchema).where(
                InvoiceSchema.credit_card_id == credit_card_id,
                InvoiceSchema.reference_month == month,
                InvoiceSchema.reference_year == year,
                InvoiceSchema.deleted_at == None,  # noqa: E711
            )
        ).scalar_one_or_none()

    def find_invoices_by_card(self, credit_card_id: int) -> list[InvoiceSchema]:
        return (
            self.session.execute(
                select(InvoiceSchema)
                .where(
                    InvoiceSchema.credit_card_id == credit_card_id,
                    InvoiceSchema.deleted_at == None,  # noqa: E711
                )
                .order_by(InvoiceSchema.reference_year.desc(), InvoiceSchema.reference_month.desc())
            )
            .scalars()
            .all()
        )

    def find_invoice_by_code(self, code: UUID, account_id: int) -> InvoiceSchema | None:
        """Busca uma fatura pelo code, verificando se o cartão pertence à conta."""
        result = self.session.execute(
            select(InvoiceSchema)
            .join(CreditCardSchema, InvoiceSchema.credit_card_id == CreditCardSchema.id)
            .where(
                InvoiceSchema.code == code,
                CreditCardSchema.account_id == account_id,
                InvoiceSchema.deleted_at == None,  # noqa: E711
            )
        ).scalar_one_or_none()
        return result

    def get_or_create_invoice(
        self, credit_card_id: int, month: int, year: int
    ) -> InvoiceSchema:
        """Retorna a fatura existente ou cria uma nova para o ciclo informado."""
        invoice = self.find_invoice(credit_card_id, month, year)
        if invoice:
            return invoice

        invoice = InvoiceSchema(
            credit_card_id=credit_card_id,
            reference_month=month,
            reference_year=year,
            total_amount=0,
            is_paid=False,
        )
        self.session.add(invoice)
        self.session.flush()
        return invoice

    def update_invoice_total(self, invoice_id: int, total_amount: int) -> None:
        invoice = self.session.get(InvoiceSchema, invoice_id)
        if invoice:
            invoice.total_amount = total_amount
            self.session.commit()

    def mark_invoice_paid(self, invoice: InvoiceSchema) -> InvoiceSchema:
        invoice.is_paid = True
        self.session.commit()
        self.session.refresh(invoice)
        return invoice
