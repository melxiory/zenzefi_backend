#!/usr/bin/env python3
"""
Check database connection and tables
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine
from sqlalchemy import text

def main():
    """Check database connection and tables"""
    print('=' * 50)
    print('DATABASE CONNECTION CHECK')
    print('=' * 50)

    with engine.connect() as conn:
        # Get database name
        result = conn.execute(text("SELECT current_database();"))
        db_name = result.scalar()
        print(f'\nConnected to database: {db_name}')

        # List all tables
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """))

        tables = [row[0] for row in result]
        print(f'\nTables in database ({len(tables)}):')
        for table in tables:
            print(f'  - {table}')

        if 'users' in tables:
            # Count users
            result = conn.execute(text("SELECT COUNT(*) FROM users;"))
            user_count = result.scalar()
            print(f'\nUsers: {user_count}')

        if 'access_tokens' in tables:
            # Count tokens
            result = conn.execute(text("SELECT COUNT(*) FROM access_tokens;"))
            token_count = result.scalar()
            print(f'Tokens: {token_count}')

if __name__ == '__main__':
    main()
