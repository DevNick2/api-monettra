from dotenv import dotenv_values

import os

env = os.environ.get('PYTHON_ENV', 'development')

environment = dotenv_values(f'.env.{env}')