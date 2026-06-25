import sys
import os

# Add your path to new folder / Добавляем путь к вашему приложению
path = '/home/YOURNAME/mysite'
if path not in sys.path:
    sys.path.append(path)

from app import app as application