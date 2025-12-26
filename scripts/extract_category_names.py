import os
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from app.models import BookCategory

# 환경 변수 로드
env_path = os.path.join(os.path.dirname(__file__), '../.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
DB_URL = os.getenv('DATABASE_URL', 'mysql+pymysql://root:password@localhost:3306/bookstopper')
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
session = Session()

def main():
    names = session.query(BookCategory.category_name).distinct().all()
    for (name,) in sorted(names):
        print(name)

if __name__ == '__main__':
    main()
