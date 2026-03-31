from dependency_injector import containers, providers
from sqlalchemy.orm import sessionmaker

from src.repository.user_repository import UserRepository
from src.repository.transaction_repository import TransactionRepository
from src.repository.category_repository import CategoryRepository
from src.repository.account_repository import AccountRepository
from src.repository.ofx_import_repository import OfxImportRepository
from src.repository.credit_card_repository import CreditCardRepository
from src.modules.auth.auth_service import AuthService
from src.modules.transactions.transactions_service import TransactionsService
from src.modules.categories.categories_service import CategoriesService
from src.modules.analytics.analytics_service import AnalyticsService
from src.repository.analytics_repository import AnalyticsRepository
from src.shared.services.redis_service import RedisService
from src.modules.planning.planning_service import PlanningService
from src.repository.subscription_repository import SubscriptionRepository
from src.modules.subscriptions.subscriptions_service import SubscriptionsService
from src.modules.accounts.accounts_service import AccountsService
from src.shared.services.ia_service import IaService
from src.modules.ia_engine.ia_engine_service import IaEngineService
from src.modules.credit_cards.credit_cards_service import CreditCardsService
from src.modules.users.users_service import UsersService

from .postgres_services import PostgresServices


def init_db_session(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


class ContainerService(containers.DeclarativeContainer):
    config = providers.Configuration()

    # ---------------------------------------------------------------------------
    # Banco de dados
    # ---------------------------------------------------------------------------
    db_service = providers.Singleton(
        PostgresServices,
        dbname=config.db.dbname,
        port=config.db.port,
        host=config.db.host,
        user=config.db.user,
        password=config.db.password
    )

    engine = providers.Singleton(
        lambda postgresService: postgresService.connection(), db_service
    )

    session_factory = providers.Singleton(
        sessionmaker,
        bind=engine,
            autoflush=True,
            expire_on_commit=False
    )

    # ---------------------------------------------------------------------------
    # Gerenciamento de Sessão com Fechamento Automático (Prevenção de Timeout)
    # ---------------------------------------------------------------------------
    db = providers.Resource(
        init_db_session,
        session_factory=session_factory
    )

    # ---------------------------------------------------------------------------
    # Repositories
    # ---------------------------------------------------------------------------
    userRepository = providers.Factory(UserRepository, dbSession=db)
    transaction_repository = providers.Factory(TransactionRepository, dbSession=db)
    category_repository = providers.Factory(CategoryRepository, dbSession=db)
    analytics_repository = providers.Factory(AnalyticsRepository, db_session=db)
    subscription_repository = providers.Factory(SubscriptionRepository, dbSession=db)
    account_repository = providers.Factory(AccountRepository, dbSession=db)
    ofx_import_repository = providers.Factory(OfxImportRepository, dbSession=db)
    credit_card_repository = providers.Factory(CreditCardRepository, dbSession=db)

    # ---------------------------------------------------------------------------
    # Cache
    # ---------------------------------------------------------------------------
    redis_service = providers.Singleton(RedisService)

    # ---------------------------------------------------------------------------
    # IA
    # ---------------------------------------------------------------------------
    ia_service = providers.Singleton(IaService)

    # ---------------------------------------------------------------------------
    # Services
    # ---------------------------------------------------------------------------
    users_service = providers.Factory(UsersService, repository=userRepository)
    auth_service = providers.Factory(AuthService, repository=userRepository)
    transactions_service = providers.Factory(
        TransactionsService,
        repository=transaction_repository,
        cache=redis_service,
        ia=ia_service
    )
    categories_service = providers.Factory(
        CategoriesService,
        repository=category_repository,
    )
    analytics_service = providers.Factory(
        AnalyticsService,
        repository=analytics_repository,
    )
    planning_service = providers.Factory(
        PlanningService,
        transaction_repository=transaction_repository,
        cache=redis_service,
    )
    subscriptions_service = providers.Factory(
        SubscriptionsService,
        repository=subscription_repository,
        transaction_repository=transaction_repository,
        cache=redis_service,
    )
    accounts_service = providers.Factory(
        AccountsService,
        repository=account_repository,
        user_repository=userRepository,
    )
    ia_engine_service = providers.Factory(
        IaEngineService,
        ia=ia_service,
        ofx_import_repository=ofx_import_repository,
        cache=redis_service,
    )
    credit_cards_service = providers.Factory(
        CreditCardsService,
        repository=credit_card_repository,
        transaction_repository=transaction_repository,
        cache=redis_service,
    )
