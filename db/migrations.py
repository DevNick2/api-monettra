from src.shared.utils.environment import environment
from sqlalchemy import Engine
from src.schemas.base import Base

import src.schemas

from src.shared.services.di_services import ContainerService

def main():
  db_config = {
    "dbname": environment.get('DATABASE_DB'),
    "user": environment.get('DATABASE_USER'),
    "password": environment.get('DATABASE_PASSWORD'),
    "host": environment.get('DATABASE_HOST'),
    "port": environment.get('DATABASE_PORT'),
  }

  container = ContainerService()
  container.config.db.from_dict(db_config)
  engine: Engine = container.engine()
  Base.metadata.create_all(bind=engine)
  

if __name__ == "__main__":
  main()