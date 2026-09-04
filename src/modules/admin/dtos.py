from datetime import datetime

from pydantic import UUID4, BaseModel, EmailStr


class AccountSummary(BaseModel):
    name: str
    max_members: int
    is_active: bool

    model_config = {"from_attributes": True}


class AccountMemberSummary(BaseModel):
    code: UUID4
    name: str | None
    email: str
    role: str
    is_accepted: bool

    model_config = {"from_attributes": True}


class UserAdminListResponse(BaseModel):
    code: UUID4
    name: str | None
    email: str
    type: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserAdminDetailResponse(UserAdminListResponse):
    account: AccountSummary | None = None
    members: list[AccountMemberSummary] = []


class CreateUserAdminDTO(BaseModel):
    name: str
    email: EmailStr
    password: str
    type: str = "user"


class UpdateUserAdminDTO(BaseModel):
    name: str | None = None
    email: EmailStr | None = None


class PaginatedUsersResponse(BaseModel):
    items: list[UserAdminListResponse]
    total: int
    page: int
    page_size: int


# ── Token Usage ──────────────────────────────────────────────


class TokenUsageAggregatedResponse(BaseModel):
    account_code: str
    account_name: str | None
    total_input: int
    total_output: int
    call_count: int


class TokenUsageDetailResponse(BaseModel):
    operation: str
    model: str
    tokens_input: int
    tokens_output: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedTokenUsageResponse(BaseModel):
    items: list[TokenUsageDetailResponse]
    total: int
    page: int
    page_size: int


# ── Feature Flags ────────────────────────────────────────────


class FeatureFlagAdminResponse(BaseModel):
    name: str
    description: str | None
    enabled_global: bool
    override_count: int

    model_config = {"from_attributes": True}


class AccountFeatureFlagResponse(BaseModel):
    account_code: str
    account_name: str | None
    flag_name: str
    enabled: bool

    model_config = {"from_attributes": True}


class UpdateFeatureFlagDTO(BaseModel):
    enabled_global: bool


class UpsertOverrideDTO(BaseModel):
    enabled: bool
