from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.schemas.feature_flags import AccountFeatureFlagSchema, FeatureFlagSchema


class FeatureFlagRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def list_all(self) -> list[FeatureFlagSchema]:
        return self.session.execute(
            select(FeatureFlagSchema).order_by(FeatureFlagSchema.name)
        ).scalars().all()

    def get_by_name(self, name: str) -> FeatureFlagSchema | None:
        return self.session.execute(
            select(FeatureFlagSchema).where(FeatureFlagSchema.name == name)
        ).scalar_one_or_none()

    def update_global(self, name: str, enabled: bool) -> FeatureFlagSchema | None:
        flag = self.get_by_name(name)
        if flag:
            flag.enabled_global = enabled
            self.session.commit()
            self.session.refresh(flag)
        return flag

    def list_overrides(self, flag_name: str) -> list[AccountFeatureFlagSchema]:
        return self.session.execute(
            select(AccountFeatureFlagSchema).where(
                AccountFeatureFlagSchema.flag_name == flag_name
            )
        ).scalars().all()

    def get_override(
        self, account_id: int, flag_name: str
    ) -> AccountFeatureFlagSchema | None:
        return self.session.execute(
            select(AccountFeatureFlagSchema).where(
                AccountFeatureFlagSchema.account_id == account_id,
                AccountFeatureFlagSchema.flag_name == flag_name,
            )
        ).scalar_one_or_none()

    def upsert_override(
        self, account_id: int, flag_name: str, enabled: bool
    ) -> AccountFeatureFlagSchema:
        override = self.get_override(account_id, flag_name)
        if override:
            override.enabled = enabled
            self.session.commit()
            self.session.refresh(override)
        else:
            override = AccountFeatureFlagSchema(
                account_id=account_id,
                flag_name=flag_name,
                enabled=enabled,
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(override)
            self.session.commit()
            self.session.refresh(override)
        return override

    def delete_override(self, account_id: int, flag_name: str) -> bool:
        override = self.get_override(account_id, flag_name)
        if override:
            self.session.delete(override)
            self.session.commit()
            return True
        return False

    def enabled_for_account(self, flag_name: str, account_id: int) -> bool:
        """Retorna enabled do override se existir, senão retorna enabled_global."""
        override = self.get_override(account_id, flag_name)
        if override is not None:
            return override.enabled
        flag = self.get_by_name(flag_name)
        if flag is None:
            return True
        return flag.enabled_global
