from dependency_injector import containers, providers
from sqlalchemy.orm import sessionmaker

from src.repository.user_repository import UserRepository
from src.repository.transaction_repository import TransactionRepository
from src.repository.category_repository import CategoryRepository
from src.modules.auth.auth_service import AuthService
from src.modules.transactions.transactions_service import TransactionsService
from src.modules.categories.categories_service import CategoriesService
from src.modules.analytics.analytics_service import AnalyticsService
from src.repository.analytics_repository import AnalyticsRepository
from src.shared.services.redis_service import RedisService
from src.modules.planning.planning_service import PlanningService

from .postgres_services import PostgresServices


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

    db = providers.Factory(session_factory)

    # ---------------------------------------------------------------------------
    # Repositories
    # ---------------------------------------------------------------------------
    userRepository = providers.Singleton(UserRepository, dbSession=db)
    transaction_repository = providers.Singleton(TransactionRepository, dbSession=db)
    category_repository = providers.Singleton(CategoryRepository, dbSession=db)
    analytics_repository = providers.Singleton(AnalyticsRepository, db_session=db)

    # ---------------------------------------------------------------------------
    # Cache
    # ---------------------------------------------------------------------------
    redis_service = providers.Singleton(RedisService)

    # ---------------------------------------------------------------------------
    # Services
    # ---------------------------------------------------------------------------
    auth_service = providers.Singleton(AuthService, repository=userRepository)
    transactions_service = providers.Singleton(
        TransactionsService,
        repository=transaction_repository,
        cache=redis_service,
    )
    categories_service = providers.Singleton(
        CategoriesService,
        repository=category_repository,
    )
    analytics_service = providers.Singleton(
        AnalyticsService,
        repository=analytics_repository,
    )

    planning_service = providers.Singleton(
        PlanningService,
        transaction_repository=transaction_repository,
        cache=redis_service,
    )
