from sqlalchemy import create_engine
from src.shared.utils.logger import logger

class PostgresServices:
  def __init__(self, dbname: str, user: str, password: str, host: str, port=5432):
    DATABASE_URL = f'postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}'

    self.engine = create_engine(DATABASE_URL)
  
  def connection(self):
    try:
      with self.engine.connect() as connection:
        logger.info('Database connected!')
        return self.engine
    except Exception as e:
        logger.error(f'Error during connection database: {e}')


  # def connect(self):
  #   try:
  #     self.connection = psycopg.connect(self.conn_string)
  #     logger.info('Connected to the PostgreSQL')
  #   except psycopg.Error as e:
  #     logger.error(f'Error connection to the database: {e}')
  #     self.connection = None

  # def disconnect(self):    
  #   if self.connection:
  #     self.connection.close()
  #     logger.info('Disconnected from the Database')
  #     self.connection = None

  # def executeQuery(self, query, params=None):
  #   if not self.connection:
  #     logger.error('Not connected to the database')
    
  #   try:
  #     with self.connection.cursor() as cur:
  #       cur.execute(query, params)
  #       if cur.description: # Verifica se tem resultados (e.g Select)
  #         return cur.fetchall()
  #       else: # Para comandos Insert, Update, delete ...
  #         self.connection.commit()
  #         return True
  #   except psycopg.errors as e:
  #     logger.error(f'Error execution query: {e}')
  #     self.connection.rollback() # Rollaback quando erro
  #     return None
